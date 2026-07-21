"""NPC commands + the queries the spec demands (FR-6).

Every fact about an NPC's movement, death, or acquaintance with the party enters as a domain
event; the projectors in ``projectors.py`` fold those into the cached columns this module
reads. So the write path here is thin: validate, ``ctx.emit``, done.

Itineraries (FR-6.5) compile to scheduled events **lazily** (docs/07 §9.6). The time engine
calls ``materialize_due`` before its firing loop, so a daily route only ever enqueues the
occurrences inside the window the clock is about to cross.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.core.pipeline import CommandContext, command_tx
from app.modules.campaign.models import Campaign
from app.modules.npcs.models import Npc, NpcLocationHistory, NpcSchedule
from app.modules.npcs.schemas import (
    NPC_STATUSES,
    HistoryRow,
    NpcCreate,
    NpcOut,
    NpcUpdate,
    ScheduleCreate,
    ScheduleOut,
    ScheduleStop,
    WhereOut,
)
from app.modules.rules.models import StatBlock
from app.modules.time import scheduled
from app.modules.time import service as time_service
from app.modules.time.calendar import CalendarMath
from app.modules.time.models import ScheduledEvent
from app.modules.wiki import service as wiki_service
from app.modules.wiki.models import Entity, Link
from app.modules.wiki.schemas import EntityCreate

KNOWS_ABOUT = "knows_about"
MOVE_ACTION = "move_npc"
#: One materialize call never enqueues more than this — a mis-typed itinerary can't OOM us.
MATERIALIZE_CEILING = 500


class NpcError(ValueError):
    pass


class NpcNotFound(LookupError):
    pass


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def ensure_npc_rows(session: Session, campaign_id: str) -> None:
    """Back-fill the extension row for 'npc' entities born in the plain entity API."""
    missing = session.scalars(
        select(Entity.id).where(
            Entity.campaign_id == campaign_id,
            Entity.entity_type == "npc",
            Entity.deleted_at_real.is_(None),
            Entity.id.not_in(select(Npc.entity_id).where(Npc.campaign_id == campaign_id)),
        )
    ).all()
    if not missing:
        return
    for entity_id in missing:
        # An existing `located_at` edge is the best guess at where they already are.
        location_id = session.scalar(
            select(Link.to_entity).where(
                Link.from_entity == entity_id, Link.link_type_id == "located_at"
            )
        )
        session.add(Npc(
            entity_id=entity_id, campaign_id=campaign_id, current_location_id=location_id
        ))
    session.commit()


def _require(session: Session, campaign_id: str, npc_id: str) -> Npc:
    npc = session.get(Npc, npc_id)
    if npc is None:
        ensure_npc_rows(session, campaign_id)
        npc = session.get(Npc, npc_id)
    if npc is None or npc.campaign_id != campaign_id:
        raise NpcNotFound(npc_id)
    return npc


def _entity(session: Session, entity_id: str) -> Entity:
    entity = session.get(Entity, entity_id)
    if entity is None:  # pragma: no cover - FK guarantees this
        raise NpcNotFound(entity_id)
    return entity


def _name_of(session: Session, entity_id: str | None) -> str | None:
    if entity_id is None:
        return None
    entity = session.get(Entity, entity_id)
    return entity.name if entity is not None else None


def _knows_about(session: Session, npc_id: str) -> list[str]:
    return list(
        session.scalars(
            select(Link.to_entity).where(
                Link.from_entity == npc_id, Link.link_type_id == KNOWS_ABOUT
            )
        )
    )


def _out(session: Session, npc: Npc) -> NpcOut:
    entity = _entity(session, npc.entity_id)
    block = session.get(StatBlock, npc.stat_block_id) if npc.stat_block_id else None
    return NpcOut(
        entity_id=npc.entity_id, name=entity.name, summary=entity.summary,
        status=npc.status, current_location_id=npc.current_location_id,
        current_location_name=_name_of(session, npc.current_location_id),
        has_met_party=bool(npc.has_met_party),
        last_party_interaction_game=npc.last_party_interaction_game,
        goals=npc.goals, secrets=npc.secrets, voice_notes=npc.voice_notes,
        knows_about=_knows_about(session, npc.entity_id),
        stat_block_id=npc.stat_block_id,
        stat_block_label=block.label if block else None,
        deleted=entity.deleted_at_real is not None,
    )


def get_npc(session: Session, campaign_id: str, npc_id: str) -> NpcOut:
    return _out(session, _require(session, campaign_id, npc_id))


def list_npcs(
    session: Session,
    campaign_id: str,
    *,
    status: str | None = None,
    location_id: str | None = None,
    faction_id: str | None = None,
    met_party: bool | None = None,
    knows: str | None = None,
    include_deleted: bool = False,
) -> list[NpcOut]:
    """The saved-query surface (FR-6.6): status / location / faction / met / knows-X."""
    ensure_npc_rows(session, campaign_id)
    # Soft-deleting a wiki entity only stamps `deleted_at_real`; the Npc row survives, so
    # without this join a deleted NPC keeps showing up here (and in every saved query built
    # on it) looking exactly like a live one. `include_deleted` mirrors the entity list, so
    # a deleted NPC is still reachable for restoring.
    stmt = (
        select(Npc)
        .where(Npc.campaign_id == campaign_id)
        .join(Entity, Entity.id == Npc.entity_id)
    )
    if not include_deleted:
        stmt = stmt.where(Entity.deleted_at_real.is_(None))
    if status:
        stmt = stmt.where(Npc.status == status)
    if location_id:
        stmt = stmt.where(Npc.current_location_id == location_id)
    if met_party is not None:
        stmt = stmt.where(Npc.has_met_party == met_party)
    if faction_id:
        stmt = stmt.where(
            Npc.entity_id.in_(
                select(Link.from_entity).where(
                    Link.link_type_id == "member_of", Link.to_entity == faction_id
                )
            )
        )
    if knows:
        stmt = stmt.where(
            Npc.entity_id.in_(
                select(Link.from_entity).where(
                    Link.link_type_id == KNOWS_ABOUT, Link.to_entity == knows
                )
            )
        )
    npcs = list(session.scalars(stmt))
    npcs.sort(key=lambda n: _entity(session, n.entity_id).name)
    return [_out(session, n) for n in npcs]


def _history_row(session: Session, cal: CalendarMath, row: NpcLocationHistory) -> HistoryRow:
    return HistoryRow(
        location_id=row.location_id,
        location_name=_name_of(session, row.location_id),
        from_game=row.from_game, from_label=cal.format(row.from_game)["label"],
        to_game=row.to_game,
        to_label=cal.format(row.to_game)["label"] if row.to_game is not None else None,
    )


def history(session: Session, campaign: Campaign, npc_id: str) -> list[HistoryRow]:
    _require(session, campaign.id, npc_id)
    cal = time_service.calendar_for(campaign)
    rows = session.scalars(
        select(NpcLocationHistory)
        .where(NpcLocationHistory.npc_id == npc_id)
        .order_by(NpcLocationHistory.from_game)
    )
    return [_history_row(session, cal, r) for r in rows]


def where_was(
    session: Session,
    campaign: Campaign,
    npc_id: str,
    *,
    at_game: int | None = None,
    window: tuple[int, int] | None = None,
) -> WhereOut:
    """Where the NPC was at an instant, or everywhere they were across a window.

    Intervals are half-open ``[from_game, to_game)``, so a single instant matches exactly
    one row — one indexed range probe, no scan (docs/05 §7.9).
    """
    _require(session, campaign.id, npc_id)  # 404s for an unknown NPC before we query history
    cal = time_service.calendar_for(campaign)
    stmt = select(NpcLocationHistory).where(NpcLocationHistory.npc_id == npc_id)
    if at_game is not None:
        stmt = stmt.where(
            NpcLocationHistory.from_game <= at_game,
            (NpcLocationHistory.to_game.is_(None)) | (NpcLocationHistory.to_game > at_game),
        )
    elif window is not None:
        start, end = window
        stmt = stmt.where(
            NpcLocationHistory.from_game < end,
            (NpcLocationHistory.to_game.is_(None)) | (NpcLocationHistory.to_game > start),
        )
    rows = session.scalars(stmt.order_by(NpcLocationHistory.from_game))
    return WhereOut(
        npc_id=npc_id, name=_entity(session, npc_id).name,
        places=[_history_row(session, cal, r) for r in rows],
        at_game=at_game,
    )


def who_knows(session: Session, campaign_id: str, topic_entity_id: str) -> list[NpcOut]:
    return list_npcs(session, campaign_id, knows=topic_entity_id)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def create_npc(
    session: Session, campaign: Campaign, data: NpcCreate, *, created_by: str
) -> NpcOut:
    if data.status not in NPC_STATUSES:
        raise NpcError(f"unknown status: {data.status}")
    entity = wiki_service.create_entity(
        session, campaign.id,
        data=EntityCreate(entity_type="npc", name=data.name, summary=data.summary),
        created_by=created_by,
    )
    session.add(Npc(
        entity_id=entity.id, campaign_id=campaign.id, status=data.status,
        goals=data.goals, secrets=data.secrets,
    ))
    session.commit()
    if data.location_id:
        relocate(session, campaign, entity.id, data.location_id, reason="introduced")
    return get_npc(session, campaign.id, entity.id)


def update_npc(session: Session, campaign_id: str, npc_id: str, data: NpcUpdate) -> NpcOut:
    npc = _require(session, campaign_id, npc_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("stat_block_id"):
        block = session.get(StatBlock, changes["stat_block_id"])
        if block is None or block.campaign_id != campaign_id:
            raise NpcError("stat block not found in this campaign")
        # An NPC's sheet is an NPC sheet: a monster block carries a CR and no class levels,
        # and the sheet editor that authors these only ever writes sheet_type="npc".
        if block.sheet_type != "npc":
            raise NpcError(f"a {block.sheet_type} sheet cannot be an NPC's stat block")
    for key, value in changes.items():
        setattr(npc, key, value)
    session.commit()
    return get_npc(session, campaign_id, npc_id)


def _emit_relocation(
    ctx: CommandContext,
    npc: Npc,
    name: str,
    from_name: str | None,
    to_id: str | None,
    to_name: str | None,
    reason: str | None,
    at_time: int | None = None,
) -> None:
    where = f"to {to_name}" if to_name else "out of sight"
    origin = f" from {from_name}" if from_name else ""
    suffix = f" ({reason})" if reason else ""
    ctx.emit(
        "npc_relocated",
        payload={"npc_id": npc.entity_id, "from": npc.current_location_id, "to": to_id,
                 "reason": reason},
        narrative=f"{name} traveled{origin} {where}{suffix}.",
        occurred_at_game=at_time,
        subject_entity_ids=(npc.entity_id,),
    )


def relocate(
    session: Session,
    campaign: Campaign,
    npc_id: str,
    location_id: str | None,
    *,
    reason: str | None = None,
) -> NpcOut:
    npc = _require(session, campaign.id, npc_id)
    if location_id is not None:
        target = session.get(Entity, location_id)
        if target is None or target.campaign_id != campaign.id:
            raise NpcError("location not found in this campaign")
    if npc.current_location_id == location_id:
        return _out(session, npc)  # idempotent; a non-move is not a fact

    name = _entity(session, npc_id).name
    from_name = _name_of(session, npc.current_location_id)
    with command_tx(session, campaign.id, actor="gm") as ctx:
        _emit_relocation(
            ctx, npc, name, from_name, location_id, _name_of(session, location_id), reason
        )
    return get_npc(session, campaign.id, npc_id)


def set_status(
    session: Session, campaign: Campaign, npc_id: str, status: str, reason: str | None = None
) -> NpcOut:
    npc = _require(session, campaign.id, npc_id)
    if status not in NPC_STATUSES:
        raise NpcError(f"unknown status: {status}")
    if status == npc.status:
        return _out(session, npc)
    name = _entity(session, npc_id).name
    suffix = f" ({reason})" if reason else ""
    with command_tx(session, campaign.id, actor="gm") as ctx:
        ctx.emit(
            "npc_status_changed",
            payload={"npc_id": npc_id, "from": npc.status, "to": status, "reason": reason},
            narrative=f"{name} is now {status}{suffix}.",
            subject_entity_ids=(npc_id,),
        )
    return get_npc(session, campaign.id, npc_id)


def record_interaction(
    session: Session, campaign: Campaign, npc_id: str, summary: str | None
) -> NpcOut:
    """The party talked to them (FR-6.4): sets has-met and stamps the interaction time."""
    npc = _require(session, campaign.id, npc_id)
    name = _entity(session, npc_id).name
    first = not npc.has_met_party
    with command_tx(session, campaign.id, actor="gm") as ctx:
        ctx.emit(
            "npc_met_party" if first else "npc_interaction",
            payload={"npc_id": npc_id, "summary": summary},
            narrative=(
                f"The party met {name}." if first
                else f"The party spoke with {name}." + (f" {summary}" if summary else "")
            ),
            subject_entity_ids=(npc_id,),
        )
    return get_npc(session, campaign.id, npc_id)


# --------------------------------------------------------------------------- #
# Itineraries (FR-6.5) — lazily compiled into the scheduled-event queue
# --------------------------------------------------------------------------- #
def _rule(schedule: NpcSchedule) -> dict[str, Any]:
    try:
        parsed: dict[str, Any] = json.loads(schedule.rule_json)
        return parsed
    except json.JSONDecodeError:  # pragma: no cover - written by us
        return {}


def _schedule_out(schedule: NpcSchedule) -> ScheduleOut:
    rule = _rule(schedule)
    return ScheduleOut(
        id=schedule.id, npc_id=schedule.npc_id, label=schedule.label,
        interval_days=int(rule.get("interval_days", 1)),
        stops=[ScheduleStop(**s) for s in rule.get("stops", [])],
        active=bool(schedule.active),
        materialized_through_game=schedule.materialized_through_game,
    )


def list_schedules(
    session: Session, campaign_id: str, npc_id: str | None = None
) -> list[ScheduleOut]:
    stmt = select(NpcSchedule).where(NpcSchedule.campaign_id == campaign_id)
    if npc_id:
        stmt = stmt.where(NpcSchedule.npc_id == npc_id)
    return [_schedule_out(s) for s in session.scalars(stmt)]


def create_schedule(
    session: Session, campaign: Campaign, npc_id: str, data: ScheduleCreate
) -> ScheduleOut:
    _require(session, campaign.id, npc_id)
    for stop in data.stops:
        target = session.get(Entity, stop.location_id)
        if target is None or target.campaign_id != campaign.id:
            raise NpcError("stop location not found in this campaign")
    schedule = NpcSchedule(
        id=new_id(), campaign_id=campaign.id, npc_id=npc_id, label=data.label,
        rule_json=json.dumps({
            "interval_days": data.interval_days,
            "stops": [s.model_dump() for s in data.stops],
        }),
        active=True,
        materialized_through_game=campaign.clock_time_game,
    )
    session.add(schedule)
    session.commit()
    return _schedule_out(schedule)


def delete_schedule(session: Session, campaign_id: str, schedule_id: str) -> None:
    schedule = session.get(NpcSchedule, schedule_id)
    if schedule is None or schedule.campaign_id != campaign_id:
        raise NpcNotFound(schedule_id)
    # Retract any occurrences already compiled but not yet fired.
    for event in session.scalars(
        select(ScheduledEvent).where(
            ScheduledEvent.campaign_id == campaign_id,
            ScheduledEvent.status == "pending",
            ScheduledEvent.action_type == MOVE_ACTION,
            ScheduledEvent.source_entity_id == schedule.npc_id,
        )
    ):
        if json.loads(event.action_json).get("schedule_id") == schedule_id:
            event.status = "cancelled"
    session.delete(schedule)
    session.commit()


def _occurrences(
    rule: dict[str, Any], seconds_per_day: int, after: int, through: int
) -> list[tuple[int, dict[str, Any]]]:
    """Every (time, stop) the rule produces in the half-open window ``(after, through]``."""
    interval = max(1, int(rule.get("interval_days", 1)))
    stops = [s for s in rule.get("stops", []) if isinstance(s, dict)]
    if not stops or through <= after:
        return []
    period = interval * seconds_per_day
    out: list[tuple[int, dict[str, Any]]] = []
    first_day = after // period
    last_day = through // period
    for day in range(first_day, last_day + 1):
        base = day * period
        for stop in stops:
            t = base + int(stop.get("at_seconds", 0))
            if after < t <= through:
                out.append((t, stop))
            if len(out) > MATERIALIZE_CEILING:
                return sorted(out[:MATERIALIZE_CEILING], key=lambda p: p[0])
    return sorted(out, key=lambda pair: pair[0])


def _pending_window(campaign: Campaign, schedule: NpcSchedule) -> int:
    after = schedule.materialized_through_game
    return campaign.clock_time_game if after is None else after


def preview_itineraries(
    session: Session, campaign: Campaign, to_time: int
) -> list[tuple[int, str]]:
    """Dry run (docs/07 §9.5): occurrences not yet compiled into the queue. No writes.

    Occurrences already materialized are pending scheduled events, so the caller previews
    them the ordinary way — reporting them here too would double-count.
    """
    seconds_per_day = time_service.calendar_for(campaign).seconds_per_day
    out: list[tuple[int, str]] = []
    for schedule in session.scalars(
        select(NpcSchedule).where(
            NpcSchedule.campaign_id == campaign.id, NpcSchedule.active.is_(True)
        )
    ):
        after = _pending_window(campaign, schedule)
        if to_time <= after:
            continue
        name = _name_of(session, schedule.npc_id) or "An NPC"
        for at_time, stop in _occurrences(_rule(schedule), seconds_per_day, after, to_time):
            place = _name_of(session, str(stop.get("location_id", ""))) or "parts unknown"
            out.append((at_time, f"{name} would travel to {place} ({schedule.label})."))
    return out


def materialize_due(session: Session, campaign: Campaign, to_time: int) -> int:
    """Compile active itineraries into scheduled events up to ``to_time`` (docs/07 §9.6).

    Called by the time engine *inside* the advance transaction, before its firing loop — so
    the occurrences this creates fire in the very same ordered pass. Never commits.
    """
    created = 0
    seconds_per_day = time_service.calendar_for(campaign).seconds_per_day
    for schedule in session.scalars(
        select(NpcSchedule).where(
            NpcSchedule.campaign_id == campaign.id, NpcSchedule.active.is_(True)
        )
    ):
        after = _pending_window(campaign, schedule)
        if to_time <= after:
            continue
        for at_time, stop in _occurrences(_rule(schedule), seconds_per_day, after, to_time):
            session.add(ScheduledEvent(
                id=new_id(), campaign_id=campaign.id, fire_at_game=at_time,
                recurrence_days=None, action_type=MOVE_ACTION,
                action_json=json.dumps({
                    "npc_id": schedule.npc_id, "location_id": stop.get("location_id"),
                    "schedule_id": schedule.id,
                }),
                title=schedule.label or "Itinerary",
                created_by_kind="npc_schedule", source_entity_id=schedule.npc_id,
                status="pending",
            ))
            created += 1
        schedule.materialized_through_game = to_time
    session.flush()
    return created


# --------------------------------------------------------------------------- #
# `move_npc` — registered with the time engine's action registry
# --------------------------------------------------------------------------- #
def _move_execute(
    session: Session,
    ctx: CommandContext,
    campaign_id: str,
    event: ScheduledEvent,
    action: dict[str, Any],
    at_time: int,
) -> str:
    """Runs inside ``advance_time``'s transaction — emit only; the projector folds state."""
    npc_id = str(action.get("npc_id", ""))
    npc = session.get(Npc, npc_id)
    if npc is None or npc.campaign_id != campaign_id:
        return f"{event.title}: that NPC no longer exists."

    location_id = action.get("location_id")
    location_id = str(location_id) if isinstance(location_id, str) else None
    name = _entity(session, npc_id).name
    if npc.status != "alive":
        return f"{name} is {npc.status}; the itinerary was skipped."
    if npc.current_location_id == location_id:
        return f"{name} is already at {_name_of(session, location_id) or 'that place'}."

    from_name = _name_of(session, npc.current_location_id)
    to_name = _name_of(session, location_id)
    _emit_relocation(ctx, npc, name, from_name, location_id, to_name, event.title, at_time)
    return f"{name} traveled to {to_name or 'parts unknown'} ({event.title})."


def _move_describe(event: ScheduledEvent, action: dict[str, Any]) -> str:
    return f"{event.title} — an NPC would relocate."


scheduled.register_action(MOVE_ACTION, execute=_move_execute, describe=_move_describe)
scheduled.register_materializer(materialize=materialize_due, preview=preview_itineraries)
