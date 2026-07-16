"""Combat run service (ADR-005): an event-sourced action log with cursor undo/redo.

Starting a combat seeds ``add_combatant`` actions from the encounter's foes and the
party's PCs. State is always derived by folding the log up to ``fold_cursor`` — so a
reload resumes exactly, and undo/redo are just cursor moves. Ending a combat summarizes
into domain events and advances the campaign clock by rounds * round length (FR-12.5).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.clock import now_real_iso
from app.core.ids import new_id
from app.core.pipeline import command_tx
from app.modules.campaign.models import Campaign
from app.modules.playbook import combat_reducer
from app.modules.playbook.models import CombatAction, CombatRun, Encounter, PartyMember
from app.modules.playbook.schemas import CombatState, CombatSummary
from app.modules.rules import registry
from app.modules.rules.models import Monster, StatBlock
from app.modules.time import service as time_service


class CombatNotFound(LookupError):
    pass


class CombatClosed(ValueError):
    pass


def _actions(session: Session, run_id: str, upto: int | None = None) -> list[CombatAction]:
    stmt = select(CombatAction).where(CombatAction.combat_run_id == run_id)
    if upto is not None:
        stmt = stmt.where(CombatAction.seq <= upto)
    return list(session.scalars(stmt.order_by(CombatAction.seq)))


def _total_actions(session: Session, run_id: str) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(CombatAction).where(
                CombatAction.combat_run_id == run_id
            )
        )
        or 0
    )


def state_of(session: Session, run: CombatRun) -> CombatState:
    actions = [json.loads(a.payload_json) for a in _actions(session, run.id, run.fold_cursor)]
    return CombatState.model_validate(combat_reducer.fold(actions))


def _require(session: Session, campaign_id: str, run_id: str) -> CombatRun:
    run = session.get(CombatRun, run_id)
    if run is None or run.campaign_id != campaign_id:
        raise CombatNotFound(run_id)
    return run


def _seed_actions(
    session: Session, campaign: Campaign, encounter_id: str | None
) -> list[dict[str, Any]]:
    """Seed combatants from the encounter's foes and the party's PCs.

    HP and initiative come from the rule system's ``combat_profile`` — this module never
    reads inside a stat-block document (docs/04 §6.8), so a system with four attributes,
    no initiative and a different HP key drops straight in.
    """
    system = registry.get_system(campaign.rule_system_id)
    seed: list[dict[str, Any]] = []

    if encounter_id:
        encounter = session.get(Encounter, encounter_id)
        if encounter is not None:
            for spec in json.loads(encounter.combatants_json):
                monster = session.get(Monster, spec["monster_id"])
                if monster is None:
                    continue
                block = session.get(StatBlock, monster.stat_block_id)
                doc = json.loads(block.doc_json) if block else {}
                profile = system.combat_profile(
                    block.sheet_type if block else "monster", doc
                )
                count = int(spec.get("count", 1))
                for n in range(count):
                    label = f"{monster.name} {n + 1}" if count > 1 else monster.name
                    seed.append({
                        "type": "add_combatant", "id": new_id(), "name": label,
                        "side": spec.get("side", "foe"), "max_hp": profile["max_hp"],
                        "initiative": profile["initiative"],
                        # Carried for the UI's stat-block panel; the reducer ignores it, so
                        # the folded state and its golden fixtures are unaffected.
                        "stat_block_id": block.id if block else None,
                    })

    # Party PCs join as allies with their live HP.
    members = session.scalars(
        select(PartyMember)
        .join(StatBlock, StatBlock.id == PartyMember.stat_block_id)
        .where(StatBlock.campaign_id == campaign.id, PartyMember.active)
    )
    for member in members:
        block = session.get(StatBlock, member.stat_block_id)
        doc = json.loads(block.doc_json) if block else {}
        status = json.loads(member.status_json)
        profile = system.combat_profile(block.sheet_type if block else "pc", doc, status)
        seed.append({
            "type": "add_combatant", "id": new_id(), "name": member.name or "PC",
            "side": "ally", "max_hp": profile["max_hp"], "hp": profile["hp"],
            "initiative": profile["initiative"], "stat_block_id": member.stat_block_id,
        })
    return seed


def combatant_blocks(session: Session, run_id: str) -> dict[str, str]:
    """Map each combatant id → its stat-block id, read from the ``add_combatant`` log.

    Cursor-independent (the seed actions are always present), so it's stable across
    undo/redo — the stat-block panel keeps working no matter where the fold sits.
    """
    out: dict[str, str] = {}
    for action in _actions(session, run_id):
        if action.action_type != "add_combatant":
            continue
        payload = json.loads(action.payload_json)
        block_id = payload.get("stat_block_id")
        if block_id:
            out[payload["id"]] = block_id
    return out


def runs_for_encounter(
    session: Session, campaign_id: str, encounter_id: str
) -> list[CombatRun]:
    """Combat runs started from an encounter, newest first (runs id-sort by ULID = time)."""
    return list(
        session.scalars(
            select(CombatRun)
            .where(
                CombatRun.campaign_id == campaign_id,
                CombatRun.encounter_id == encounter_id,
            )
            .order_by(CombatRun.id.desc())
        )
    )


def _round_length(campaign: Campaign) -> int:
    return registry.get_system(campaign.rule_system_id).round_length_seconds()


def _sync_clock(session: Session, run: CombatRun) -> None:
    """Drive the campaign clock from the combat: start + (round - 1) * round length.

    Real time is paused during combat, so each new round is exactly one round length
    (6s in 5e). Undo/redo of round changes moves the clock with them.
    """
    campaign = session.get(Campaign, run.campaign_id)
    if campaign is None:
        return
    state = state_of(session, run)
    campaign.clock_time_game = run.started_at_game + (state.round - 1) * _round_length(campaign)
    session.commit()


def start_combat(session: Session, campaign: Campaign, encounter_id: str | None) -> CombatRun:
    # Bank any elapsed real time, then pause it — combat drives the clock (6s/round).
    time_service.settle_realtime(session, campaign)
    run = CombatRun(
        id=new_id(), campaign_id=campaign.id, encounter_id=encounter_id,
        started_at_game=campaign.clock_time_game, status="active", fold_cursor=0,
    )
    session.add(run)
    session.flush()

    seed = _seed_actions(session, campaign, encounter_id)
    now = now_real_iso()
    for i, action in enumerate(seed, start=1):
        session.add(CombatAction(
            combat_run_id=run.id, seq=i, action_type=action["type"],
            payload_json=json.dumps(action), recorded_at_real=now,
        ))
    run.fold_cursor = len(seed)
    campaign.realtime_paused = True
    session.commit()
    return run


def append_action(
    session: Session, campaign_id: str, run_id: str, action_type: str, payload: dict[str, Any]
) -> CombatRun:
    run = _require(session, campaign_id, run_id)
    if run.status != "active":
        raise CombatClosed(run_id)

    # A new action after an undo truncates the redo tail.
    session.execute(
        delete(CombatAction).where(
            CombatAction.combat_run_id == run_id, CombatAction.seq > run.fold_cursor
        )
    )
    new_seq = run.fold_cursor + 1
    action = {"type": action_type, **payload}
    session.add(CombatAction(
        combat_run_id=run_id, seq=new_seq, action_type=action_type,
        payload_json=json.dumps(action), recorded_at_real=now_real_iso(),
    ))
    run.fold_cursor = new_seq
    session.commit()
    _sync_clock(session, run)
    return run


def undo(session: Session, campaign_id: str, run_id: str) -> CombatRun:
    run = _require(session, campaign_id, run_id)
    run.fold_cursor = max(0, run.fold_cursor - 1)
    session.commit()
    _sync_clock(session, run)
    return run


def redo(session: Session, campaign_id: str, run_id: str) -> CombatRun:
    run = _require(session, campaign_id, run_id)
    run.fold_cursor = min(_total_actions(session, run_id), run.fold_cursor + 1)
    session.commit()
    _sync_clock(session, run)
    return run


def _write_back_party_hp(
    session: Session, campaign: Campaign, run: CombatRun, state: CombatState
) -> None:
    """Persist what the party actually took: folded ally HP → ``PartyMember.status_json``.

    Without this the fold is the only record of a PC's wounds, and nothing reads it once the
    run is over — so a character walked out of a bruising fight at full health.

    HP goes back through the plugin (``with_hit_points``), never by writing a key into the
    status dict: 5e keys it ``current_hit_points`` and Nimble ``hp``, and the playbook is not
    allowed to know which (docs/04 §6.8).
    """
    system = registry.get_system(campaign.rule_system_id)
    blocks = combatant_blocks(session, run.id)
    members = {
        m.stat_block_id: m
        for m in session.scalars(
            select(PartyMember)
            .join(StatBlock, StatBlock.id == PartyMember.stat_block_id)
            .where(StatBlock.campaign_id == campaign.id, PartyMember.active)
        )
    }
    for cid, combatant in state.combatants.items():
        # Foes and allied NPCs have no party member to write to, and drop out here.
        member = members.get(blocks.get(cid, ""))
        if member is None:
            continue
        block = session.get(StatBlock, member.stat_block_id)
        doc = json.loads(block.doc_json) if block else {}
        status = system.with_hit_points(json.loads(member.status_json), doc, combatant.hp)
        member.status_json = json.dumps(status)


def end_combat(session: Session, campaign: Campaign, run_id: str) -> CombatSummary:
    run = _require(session, campaign.id, run_id)
    state = state_of(session, run)
    rounds = state.round
    duration = (rounds - 1) * _round_length(campaign)

    # The clock already reflects the rounds fought; make it exact and resume real time.
    campaign.clock_time_game = run.started_at_game + duration
    defeated = [c.name for c in state.combatants.values() if c.defeated and c.side == "foe"]
    with command_tx(session, campaign.id, actor="combat") as ctx:
        ctx.emit(
            "combat_ended",
            payload={"rounds": rounds, "participants": len(state.combatants),
                     "casualties": defeated},
            narrative=f"Combat ended after {rounds} round(s); {len(defeated)} foe(s) defeated.",
        )
        for name in defeated:
            ctx.emit(
                "combatant_defeated",
                payload={"name": name},
                narrative=f"{name} was defeated.",
            )
        _write_back_party_hp(session, campaign, run, state)
        run.status = "completed"
        campaign.realtime_paused = False
        if campaign.realtime_enabled:
            campaign.realtime_anchor_real = now_real_iso()  # resume real time from here

    session.refresh(campaign)
    return CombatSummary(
        rounds=rounds, duration_seconds=duration, defeated=defeated,
        to_time=campaign.clock_time_game,
    )
