"""Combat run service (ADR-005): an event-sourced action log with cursor undo/redo.

Starting a combat seeds ``add_combatant`` actions from the encounter's foes and the
party's PCs. State is always derived by folding the log up to ``fold_cursor`` — so a
reload resumes exactly, and undo/redo are just cursor moves. Ending a combat summarizes
into domain events and advances the campaign clock by rounds * round length (FR-12.5).
"""

from __future__ import annotations

import json
import random
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core import dice
from app.core.clock import now_real_iso
from app.core.ids import new_id
from app.core.pipeline import command_tx
from app.modules.campaign.models import Campaign
from app.modules.playbook import combat_reducer
from app.modules.playbook.models import (
    CombatAction,
    CombatRoll,
    CombatRun,
    Encounter,
    PartyMember,
)
from app.modules.playbook.schemas import CombatState, CombatSummary
from app.modules.rules import registry
from app.modules.rules.models import Monster, StatBlock
from app.modules.time import service as time_service

# A run in one of these is still in play — it holds the campaign in combat mode, and the
# tracker should resume it. `setup` is rolling initiative; `active` is a fight underway.
OPEN_STATUSES = frozenset({"setup", "active"})
# A run in one of these is done with: no more actions, no more undo/redo. `completed` is a
# fight that was played to its end; `abandoned` is one the GM called off (see cancel_combat).
CLOSED_STATUSES = frozenset({"completed", "abandoned"})


class CombatNotFound(LookupError):
    pass


class CombatClosed(ValueError):
    pass


class CombatantNotFound(LookupError):
    pass


class BadCombatant(ValueError):
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
                        "initiative_tiebreak": profile["initiative_mod"],
                        # Carried for the UI's stat-block panel, the initiative roll and
                        # attack resolution; the reducer ignores all three, so the folded
                        # state and its golden fixtures are unaffected.
                        "stat_block_id": block.id if block else None,
                        "initiative_dice": profile["initiative_dice"],
                        "ac": profile["ac"],
                        "legendary_max": profile["legendary"],
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
            "initiative": profile["initiative"],
            "initiative_tiebreak": profile["initiative_mod"],
            "stat_block_id": member.stat_block_id,
            "initiative_dice": profile["initiative_dice"],
            "ac": profile["ac"],
            "legendary_max": profile["legendary"],
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


def combatant_specs(session: Session, run_id: str) -> dict[str, dict[str, Any]]:
    """Map each combatant id → ``{"dice", "mod", "ac"}``, read from the ``add_combatant`` log.

    Same trick as ``combatant_blocks``: the seed actions are always in the log, so this is
    cursor-independent and keeps working across undo/redo — and it means neither rolling
    initiative nor resolving an attack has to go back to a stat block mid-combat.

    ``dice`` is None for a system that doesn't roll for order (Nimble); ``ac`` is None where
    the system has no such number (Nimble again) or for an ad-hoc combatant nobody gave one.
    """
    out: dict[str, dict[str, Any]] = {}
    for action in _actions(session, run_id):
        if action.action_type != "add_combatant":
            continue
        payload = json.loads(action.payload_json)
        out[payload["id"]] = {
            "dice": payload.get("initiative_dice"),
            "mod": int(payload.get("initiative_tiebreak", 0)),
            "ac": payload.get("ac"),
        }
    return out


def initiative_die(session: Session, run: CombatRun) -> str | None:
    """The die this system rolls for turn order, or None if it doesn't roll at all.

    The tracker needs this to know whether to *offer* rolling — Nimble's party simply acts
    first, so a "Roll initiative" button there would be a lie. Read through ``combat_profile``
    like everything else the playbook learns about a system (docs/04 §6.8).
    """
    campaign = session.get(Campaign, run.campaign_id)
    if campaign is None:
        return None
    profile = registry.get_system(campaign.rule_system_id).combat_profile("pc", {})
    die = profile.get("initiative_dice")
    return str(die) if die else None


def death_save_rules(session: Session, run: CombatRun) -> dict[str, Any]:
    """How this system handles a creature at 0 hp, or ``{"supported": False}``."""
    campaign = session.get(Campaign, run.campaign_id)
    if campaign is None:
        return {"supported": False}
    return registry.get_system(campaign.rule_system_id).death_save_rules()


def _roll_detail(result: dice.RollResult) -> dict[str, Any]:
    """The faces and modifier behind a total, so the log can show "17 (17, 9) + 5"."""
    return {
        "dice": [
            {"sides": d.sides, "value": d.value, "kept": d.kept, "sign": d.sign}
            for d in result.dice
        ],
        "modifier": result.modifier,
        "critical": result.critical,
        "fumble": result.fumble,
    }


def _append_one(session: Session, run: CombatRun, action_type: str, payload: dict[str, Any]) -> None:
    """Append without committing — for callers writing several actions in one transaction."""
    session.execute(
        delete(CombatAction).where(
            CombatAction.combat_run_id == run.id, CombatAction.seq > run.fold_cursor
        )
    )
    run.fold_cursor += 1
    session.add(CombatAction(
        combat_run_id=run.id, seq=run.fold_cursor, action_type=action_type,
        payload_json=json.dumps({"type": action_type, **payload}),
        recorded_at_real=now_real_iso(),
    ))


def _scope_ids(state: CombatState, scope: str, ids: list[str] | None) -> list[str]:
    if scope == "ids":
        return [i for i in (ids or []) if i in state.combatants]
    if scope == "foes":
        return [i for i, c in state.combatants.items() if c.side == "foe"]
    return list(state.combatants)


def roll_initiative(
    session: Session,
    campaign: Campaign,
    run_id: str,
    *,
    scope: str = "all",
    ids: list[str] | None = None,
    values: dict[str, int] | None = None,
    mode: str = "normal",
    rng: random.Random | None = None,
) -> CombatRun:
    """Roll initiative for a scope, and/or accept totals the GM typed in.

    The roll happens *here*, not in the reducer (ADR-005) — the log only ever receives the
    literal result, so folding it stays deterministic. ``values`` carries the numbers your
    players called out (modifier already included), which is why "roll the monsters and take
    my players' word for theirs" is one request rather than two.
    """
    run = _require(session, campaign.id, run_id)
    if run.status in CLOSED_STATUSES:
        raise CombatClosed(run_id)

    state = state_of(session, run)
    specs = combatant_specs(session, run_id)
    manual = {k: v for k, v in (values or {}).items() if k in state.combatants}
    now = now_real_iso()

    for cid in _scope_ids(state, scope, ids):
        # A typed total wins over a roll, and a system with no initiative die (Nimble: the
        # party simply acts first) keeps the ranking its plugin already gave us.
        spec = specs.get(cid) or {}
        die = spec.get("dice")
        if cid in manual or not die:
            continue
        mod = int(spec.get("mod", 0))
        expr = f"{die}{mod:+d}" if mod else str(die)
        result = dice.roll(expr, mode=mode, rng=rng)  # type: ignore[arg-type]
        roll_id = new_id()
        session.add(CombatRoll(
            id=roll_id, combat_run_id=run_id, combatant_id=cid, kind="initiative",
            label="Initiative", expression=expr, mode=mode,
            detail_json=json.dumps(_roll_detail(result)), total=result.total,
            recorded_at_real=now,
        ))
        _append_one(session, run, "set_initiative", {
            "id": cid, "value": result.total, "initiative_tiebreak": mod, "roll_id": roll_id,
        })

    for cid, value in manual.items():
        _append_one(session, run, "set_initiative", {
            "id": cid, "value": int(value),
            "initiative_tiebreak": int((specs.get(cid) or {}).get("mod", 0)),
        })

    session.commit()
    return run


def _next_labels(state: CombatState, base: str, count: int) -> list[str]:
    """Continue the numbering already in play: a Goblin joining Goblin 1-3 becomes Goblin 4.

    Restarting at 1 would put two "Goblin 1"s on the rail, which is exactly the moment a GM
    stops trusting the tracker to know which one is bloodied.
    """
    names = [c.name for c in state.combatants.values()]
    highest = 0
    for name in names:
        if name == base:
            highest = max(highest, 1)
        elif name.startswith(f"{base} ") and name[len(base) + 1:].isdigit():
            highest = max(highest, int(name[len(base) + 1:]))
    if highest == 0 and count == 1:
        return [base]  # the first one of its kind needs no number
    return [f"{base} {highest + i + 1}" for i in range(count)]


def add_combatant(
    session: Session,
    campaign: Campaign,
    run_id: str,
    *,
    monster_id: str | None = None,
    name: str | None = None,
    max_hp: int | None = None,
    count: int = 1,
    side: str = "foe",
    kind: str = "creature",
    initiative: int | None = None,
    rng: random.Random | None = None,
) -> CombatRun:
    """Add a straggler mid-fight: a bestiary monster, a lair, or an ad-hoc name and hit points.

    The seeding has to happen here rather than in the browser: max HP, the initiative
    modifier and the die all come from the rule system's ``combat_profile``, and the playbook
    never lets anything else read inside a stat block (docs/04 §6.8).
    """
    run = _require(session, campaign.id, run_id)
    if run.status in CLOSED_STATUSES:
        raise CombatClosed(run_id)
    system = registry.get_system(campaign.rule_system_id)
    state = state_of(session, run)

    if monster_id:
        monster = session.get(Monster, monster_id)
        if monster is None or monster.campaign_id != campaign.id:
            raise CombatantNotFound(monster_id)
        block = session.get(StatBlock, monster.stat_block_id)
        doc = json.loads(block.doc_json) if block else {}
        profile = system.combat_profile(block.sheet_type if block else "monster", doc)
        base, block_id = monster.name, (block.id if block else None)
    else:
        if not name or max_hp is None:
            raise BadCombatant("an ad-hoc combatant needs a name and max_hp")
        # No stat block to read, so the system's own die stands in and the modifier is 0 —
        # the GM can correct the number from the rail either way.
        profile = {
            "max_hp": int(max_hp), "hp": int(max_hp), "initiative": 0,
            "initiative_mod": 0, "initiative_dice": initiative_die(session, run),
            # Nobody typed an AC for a thing invented thirty seconds ago; an attack against
            # it reports the roll and lets the GM call it.
            "ac": None,
            "legendary": 0,
        }
        base, block_id = name, None

    # A lair has no die to roll — it acts on a fixed count, so nothing is left to chance.
    # Which count is the rule system's to say (5e: 20); the playbook only asks.
    if kind == "lair":
        profile = {**profile, "initiative_dice": None}
        if initiative is None and profile.get("lair_initiative") is not None:
            initiative = int(profile["lair_initiative"])

    added: list[str] = []
    for label in _next_labels(state, base, count):
        cid = new_id()
        added.append(cid)
        _append_one(session, run, "add_combatant", {
            "id": cid, "name": label, "side": side, "kind": kind,
            "max_hp": profile["max_hp"], "hp": profile["hp"],
            "initiative": profile["initiative"],
            "initiative_tiebreak": profile["initiative_mod"],
            "stat_block_id": block_id,
            "initiative_dice": profile["initiative_dice"],
            "ac": profile["ac"],
            "legendary_max": profile["legendary"],
        })
    session.commit()

    if initiative is not None:
        # An explicit number (a player's summon, say) is taken as given, never rolled over.
        for cid in added:
            _append_one(session, run, "set_initiative", {
                "id": cid, "value": int(initiative),
                "initiative_tiebreak": profile["initiative_mod"],
            })
        session.commit()
    else:
        roll_initiative(session, campaign, run_id, scope="ids", ids=added, rng=rng)
    return run


def attacks_for(
    session: Session, campaign: Campaign, run_id: str, combatant_id: str
) -> list[dict[str, Any]]:
    """The attacks this combatant can make, resolved by its rule system into plain numbers.

    Reads the stat block through ``attack_actions`` and nothing else — whether a "+7" was
    printed on a monster or worked out from a character's level is the plugin's business.
    """
    blocks = combatant_blocks(session, run_id)
    block_id = blocks.get(combatant_id)
    if block_id is None:
        return []  # an ad-hoc combatant has no sheet to read attacks off
    block = session.get(StatBlock, block_id)
    if block is None:
        return []
    system = registry.get_system(campaign.rule_system_id)
    doc = json.loads(block.doc_json)
    return [
        {"index": i, **action}
        for i, action in enumerate(system.attack_actions(block.sheet_type, doc))
    ]


def attack(
    session: Session,
    campaign: Campaign,
    run_id: str,
    *,
    attacker_id: str,
    action_index: int,
    target_id: str | None = None,
    mode: str = "normal",
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Roll an attack and report what happened. **Deliberately changes nothing.**

    The GM applies the damage (or doesn't). Resistance, cover, a ruling that the wall took
    it instead — none of that is knowable here, and auto-applying would take away the exact
    moment a GM is for. The returned damage rolls carry their ids, so applying is an ordinary
    ``damage`` action with a ``roll_id`` and the number stays traceable.
    """
    run = _require(session, campaign.id, run_id)
    if run.status in CLOSED_STATUSES:
        raise CombatClosed(run_id)
    state = state_of(session, run)
    if attacker_id not in state.combatants:
        raise CombatantNotFound(attacker_id)

    options = attacks_for(session, campaign, run_id, attacker_id)
    if not 0 <= action_index < len(options):
        raise BadCombatant(f"no attack {action_index} on {state.combatants[attacker_id].name}")
    action = options[action_index]

    target_ac: int | None = None
    if target_id:
        if target_id not in state.combatants:
            raise CombatantNotFound(target_id)
        spec = combatant_specs(session, run_id).get(target_id) or {}
        ac = spec.get("ac")
        target_ac = int(ac) if ac is not None else None

    now = now_real_iso()
    to_hit_roll: CombatRoll | None = None
    outcome: str | None = None
    hit = True

    if action.get("to_hit") is not None:
        bonus = int(action["to_hit"])
        expr = f"1d20{bonus:+d}" if bonus else "1d20"
        result = dice.roll(expr, mode=mode, rng=rng)  # type: ignore[arg-type]
        # A natural 20 hits whatever the number says, a natural 1 misses whatever it says —
        # so the faces decide before the total does.
        if result.critical:
            outcome, hit = "crit", True
        elif result.fumble:
            outcome, hit = "fumble", False
        elif target_ac is not None:
            hit = result.total >= target_ac
            outcome = "hit" if hit else "miss"
        else:
            outcome, hit = None, True  # no AC to beat: report the roll, let the GM call it
        to_hit_roll = CombatRoll(
            id=new_id(), combat_run_id=run_id, combatant_id=attacker_id, kind="attack",
            label=str(action["name"]), expression=expr, mode=mode,
            detail_json=json.dumps(_roll_detail(result)), total=result.total,
            target=target_ac, outcome=outcome, recorded_at_real=now,
        )
        session.add(to_hit_roll)

    damage_rolls: list[CombatRoll] = []
    if hit:
        for part in action.get("damage") or []:
            expr = str(part["dice"])
            if not expr or expr == "0":
                continue
            if outcome == "crit" and action.get("crit_rule") == "double_dice":
                # The system names its rule; the arithmetic is generic (app.core.dice).
                expr = dice.max_dice(expr)
            result = dice.roll(expr, rng=rng)
            roll = CombatRoll(
                id=new_id(), combat_run_id=run_id, combatant_id=target_id or attacker_id,
                kind="damage", label=f"{action['name']} ({part.get('type') or 'damage'})",
                expression=expr, mode="normal",
                detail_json=json.dumps(_roll_detail(result)), total=result.total,
                recorded_at_real=now,
            )
            session.add(roll)
            damage_rolls.append(roll)

    session.commit()
    return {
        "action_name": str(action["name"]),
        "attacker_id": attacker_id,
        "target_id": target_id,
        "target_ac": target_ac,
        "outcome": outcome,
        "to_hit": to_hit_roll,
        "damage": damage_rolls,
        "total_damage": sum(r.total for r in damage_rolls),
        "save": action.get("save"),
        "description": action.get("description"),
    }


def roll_death_save(
    session: Session,
    campaign: Campaign,
    run_id: str,
    combatant_id: str,
    *,
    rng: random.Random | None = None,
) -> CombatRun:
    """Roll one death save and record the outcome.

    The *rules* are the plugin's — which die, against what, and that a natural 20 is worth
    more than a success. This decides the outcome from those and hands the reducer a literal
    word, so folding the log stays deterministic (ADR-005).
    """
    run = _require(session, campaign.id, run_id)
    if run.status in CLOSED_STATUSES:
        raise CombatClosed(run_id)
    state = state_of(session, run)
    if combatant_id not in state.combatants:
        raise CombatantNotFound(combatant_id)

    rules = registry.get_system(campaign.rule_system_id).death_save_rules()
    if not rules.get("supported"):
        raise BadCombatant("this rule system has no death saves")

    dc = int(rules["dc"])
    result = dice.roll(str(rules["dice"]), rng=rng)
    if result.critical:
        outcome = "crit_success"
    elif result.fumble:
        outcome = "crit_fail"
    else:
        outcome = "success" if result.total >= dc else "failure"

    roll_id = new_id()
    session.add(CombatRoll(
        id=roll_id, combat_run_id=run_id, combatant_id=combatant_id, kind="death_save",
        label="Death save", expression=str(rules["dice"]), mode="normal",
        detail_json=json.dumps(_roll_detail(result)), total=result.total,
        target=dc, outcome=outcome, recorded_at_real=now_real_iso(),
    ))
    _append_one(session, run, "death_save", {
        "id": combatant_id, "result": outcome, "roll_id": roll_id,
    })
    session.commit()
    return run


def begin_combat(session: Session, campaign_id: str, run_id: str) -> CombatRun:
    """Leave setup and start round 1. Idempotent; a completed run cannot go back."""
    run = _require(session, campaign_id, run_id)
    if run.status in CLOSED_STATUSES:
        raise CombatClosed(run_id)
    run.status = "active"
    session.commit()
    return run


def rolls_for(session: Session, run_id: str, limit: int = 50) -> list[CombatRoll]:
    """The run's roll log, newest first. Append-only and outside the fold, so undo never
    erases a roll — a die that hit the table cannot be un-thrown."""
    return list(
        session.scalars(
            select(CombatRoll)
            .where(CombatRoll.combat_run_id == run_id)
            .order_by(CombatRoll.id.desc())
            .limit(limit)
        )
    )


def open_runs(session: Session, campaign_id: str) -> list[CombatRun]:
    """Runs still in play, newest first. A run rolling initiative counts: it hasn't begun,
    but it is very much in play, and the campaign is already paused for it.

    Ordered by id, not ``started_at_game``: ULIDs sort by creation time, whereas game time
    is 0 for every run in a campaign whose clock never moved — which made "the newest run"
    arbitrary exactly where it mattered.
    """
    return list(
        session.scalars(
            select(CombatRun)
            .where(CombatRun.campaign_id == campaign_id, CombatRun.status.in_(OPEN_STATUSES))
            .order_by(CombatRun.id.desc())
        )
    )


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
        started_at_game=campaign.clock_time_game, status="setup", fold_cursor=0,
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

    # The monsters roll the moment you call for initiative — that is what happens at the
    # table. The PCs' numbers are the GM's to type in, so they keep their seeded ranking
    # until then, and the run waits in `setup` until Begin.
    roll_initiative(session, campaign, run.id, scope="foes")
    return run


def append_action(
    session: Session, campaign_id: str, run_id: str, action_type: str, payload: dict[str, Any]
) -> CombatRun:
    run = _require(session, campaign_id, run_id)
    # Only a finished run is closed to writes: `setup` still takes actions, since that is
    # where initiative gets rolled and corrected before round 1 begins.
    if run.status in CLOSED_STATUSES:
        raise CombatClosed(run_id)

    # A new action after an undo truncates the redo tail.
    _append_one(session, run, action_type, payload)
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


def cancel_combat(session: Session, campaign: Campaign, run_id: str) -> None:
    """Call the fight off: the run closes, and the campaign goes back to exploration.

    The opposite of ``end_combat`` in every way that matters. A cancelled fight didn't
    happen, so nothing is written back — no party HP, no chronicle entry, no clock
    advance. The clock rewinds to where the combat started and real time resumes, which
    is what takes the campaign out of combat mode (``realtime_paused`` is the flag the
    dashboard reads to force the combat preset).

    The action log stays put. It is the record of a run that was abandoned, and deleting
    it would strand the rolls that reference it.

    Idempotent: cancelling an already-closed run is a no-op, so a double-click can't
    rewind the clock out from under a fight that legitimately ended.
    """
    run = _require(session, campaign.id, run_id)
    if run.status in CLOSED_STATUSES:
        return
    campaign.clock_time_game = run.started_at_game
    run.status = "abandoned"
    campaign.realtime_paused = False
    if campaign.realtime_enabled:
        campaign.realtime_anchor_real = now_real_iso()  # resume real time from here
    session.commit()


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
