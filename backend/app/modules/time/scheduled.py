"""Scheduled events + the ordered firing loop (docs/07, §9.3).

The loop runs *inside* the ``advance_time`` command transaction, so the clock move, the
fired events' consequences, and the resulting domain events all commit atomically
(FR-5.6). Time flows *through* events in chronological order; recurring events re-queue
and may fire again within the same window.

**Action registry.** ``narrate`` and ``set_flag`` are built in here. Richer consequences
(quest deadlines, NPC moves) belong to modules *above* time, which register a handler at
import time — the same inversion the projection registry uses (``app.core.projections``).
Time therefore never imports playbook, and the layering contract holds.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.core.pipeline import CommandContext
from app.modules.campaign import flags as campaign_flags
from app.modules.campaign.models import Campaign
from app.modules.time.calendar import CalendarMath
from app.modules.time.models import ScheduledEvent
from app.modules.time.schemas import (
    FiredEvent,
    ScheduledEventCreate,
    ScheduledEventOut,
    ScheduledEventUpdate,
)

# Protects against a mis-configured recurrence firing forever (docs/07, §9.3).
FIRING_CEILING = 10_000


class RunawayGuard(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Action registry
# --------------------------------------------------------------------------- #
#: Mutates state, emits the domain event(s), and returns the narrative it used.
Execute = Callable[[Session, CommandContext, str, ScheduledEvent, dict[str, Any], int], str]
#: The read-only twin used by the dry-run preview (§9.5) — must not write.
Describe = Callable[[ScheduledEvent, dict[str, Any]], str]


@dataclass(frozen=True)
class ActionHandler:
    execute: Execute
    describe: Describe


_ACTIONS: dict[str, ActionHandler] = {}


def register_action(action_type: str, *, execute: Execute, describe: Describe) -> None:
    _ACTIONS[action_type] = ActionHandler(execute=execute, describe=describe)


def action_types() -> list[str]:
    return sorted(_ACTIONS)


# --------------------------------------------------------------------------- #
# Materializer registry
# --------------------------------------------------------------------------- #
# Recurring *rules* that live in another module (NPC itineraries, docs/07 §9.6) are compiled
# into scheduled events only for the window the clock is about to cross — a daily route never
# enqueues a year of rows. The owning module registers the compiler here; time stays ignorant
# of what a rule means.
#: ``(session, campaign, to_time) -> rows created``. Runs in the advance tx; must not commit.
Materialize = Callable[[Session, Campaign, int], int]
#: The read-only twin: what the compiler *would* produce, as ``(at_time, narrative)`` pairs.
PreviewRules = Callable[[Session, Campaign, int], list[tuple[int, str]]]


@dataclass(frozen=True)
class MaterializerHandler:
    materialize: Materialize
    preview: PreviewRules


_MATERIALIZERS: list[MaterializerHandler] = []


def register_materializer(*, materialize: Materialize, preview: PreviewRules) -> None:
    _MATERIALIZERS.append(MaterializerHandler(materialize=materialize, preview=preview))


def _handler(action_type: str) -> ActionHandler:
    """Unknown action types degrade to a narration rather than stalling the clock."""
    return _ACTIONS.get(action_type) or _ACTIONS["narrate"]


# --- built-ins ------------------------------------------------------------- #
def _narrate_execute(
    _session: Session,
    ctx: CommandContext,
    _campaign_id: str,
    event: ScheduledEvent,
    action: dict[str, Any],
    at_time: int,
) -> str:
    narrative = str(action.get("text") or event.title)
    ctx.emit(
        "world_event",
        payload={"title": event.title, "scheduled_event_id": event.id},
        narrative=narrative,
        occurred_at_game=at_time,
    )
    return narrative


def _narrate_describe(event: ScheduledEvent, action: dict[str, Any]) -> str:
    return str(action.get("text") or event.title)


def _set_flag_execute(
    session: Session,
    ctx: CommandContext,
    campaign_id: str,
    event: ScheduledEvent,
    action: dict[str, Any],
    at_time: int,
) -> str:
    key = str(action.get("key", ""))
    value = action.get("value")
    campaign_flags.set_flag(session, campaign_id, key, value, at_game=at_time)
    narrative = f"{event.title}: flag '{key}' set to {json.dumps(value)}."
    ctx.emit(
        "flag_changed",
        payload={"key": key, "value": value, "scheduled_event_id": event.id},
        narrative=narrative,
        occurred_at_game=at_time,
    )
    return narrative


def _set_flag_describe(event: ScheduledEvent, action: dict[str, Any]) -> str:
    return f"{event.title}: set flag '{action.get('key', '')}'"


register_action("narrate", execute=_narrate_execute, describe=_narrate_describe)
register_action("set_flag", execute=_set_flag_execute, describe=_set_flag_describe)


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
def create(session: Session, campaign_id: str, data: ScheduledEventCreate) -> ScheduledEvent:
    event = ScheduledEvent(
        id=new_id(),
        campaign_id=campaign_id,
        fire_at_game=data.fire_at_game,
        recurrence_days=data.recurrence_days,
        action_type=data.action_type,
        action_json=json.dumps(data.action_json),
        title=data.title,
        created_by_kind="gm",
        status="pending",
    )
    session.add(event)
    session.commit()
    return event


def list_events(
    session: Session, campaign_id: str, *, status: str | None = None
) -> list[ScheduledEvent]:
    stmt = select(ScheduledEvent).where(ScheduledEvent.campaign_id == campaign_id)
    if status:
        stmt = stmt.where(ScheduledEvent.status == status)
    return list(session.scalars(stmt.order_by(ScheduledEvent.fire_at_game)))


def update(
    session: Session, campaign_id: str, event_id: str, data: ScheduledEventUpdate
) -> ScheduledEvent | None:
    event = session.get(ScheduledEvent, event_id)
    if event is None or event.campaign_id != campaign_id:
        return None
    fields = data.model_dump(exclude_unset=True)
    if "action_json" in fields:
        event.action_json = json.dumps(fields.pop("action_json") or {})
    for key, value in fields.items():
        setattr(event, key, value)
    session.commit()
    return event


def cancel(session: Session, campaign_id: str, event_id: str) -> bool:
    event = session.get(ScheduledEvent, event_id)
    if event is None or event.campaign_id != campaign_id:
        return False
    event.status = "cancelled"
    session.commit()
    return True


def cancel_pending_for_source(
    session: Session, campaign_id: str, source_entity_id: str, action_type: str
) -> None:
    """Cancel any pending machine-scheduled event owned by an entity (e.g. its deadline).

    Does *not* commit: callers fold this into their own transaction.
    """
    for event in session.scalars(
        select(ScheduledEvent).where(
            ScheduledEvent.campaign_id == campaign_id,
            ScheduledEvent.source_entity_id == source_entity_id,
            ScheduledEvent.action_type == action_type,
            ScheduledEvent.status == "pending",
        )
    ):
        event.status = "cancelled"


def schedule_for_source(
    session: Session,
    campaign_id: str,
    *,
    source_entity_id: str,
    action_type: str,
    action: dict[str, Any],
    fire_at_game: int,
    title: str,
    created_by_kind: str,
) -> ScheduledEvent:
    """Replace an entity's pending machine-scheduled event of this type with a new one."""
    cancel_pending_for_source(session, campaign_id, source_entity_id, action_type)
    event = ScheduledEvent(
        id=new_id(),
        campaign_id=campaign_id,
        fire_at_game=fire_at_game,
        recurrence_days=None,
        action_type=action_type,
        action_json=json.dumps(action),
        title=title,
        created_by_kind=created_by_kind,
        source_entity_id=source_entity_id,
        status="pending",
    )
    session.add(event)
    session.flush()
    return event


def to_out(cal: CalendarMath, event: ScheduledEvent) -> ScheduledEventOut:
    return ScheduledEventOut(
        id=event.id,
        title=event.title,
        fire_at_game=event.fire_at_game,
        fire_at_label=cal.format(event.fire_at_game)["label"],
        action_type=event.action_type,
        action_json=_action(event),
        recurrence_days=event.recurrence_days,
        status=event.status,
    )


# --------------------------------------------------------------------------- #
# Firing
# --------------------------------------------------------------------------- #
def _action(event: ScheduledEvent) -> dict[str, Any]:
    try:
        parsed: dict[str, Any] = json.loads(event.action_json)
        return parsed
    except (json.JSONDecodeError, TypeError):
        return {}


def _execute(
    session: Session,
    ctx: CommandContext,
    cal: CalendarMath,
    campaign_id: str,
    event: ScheduledEvent,
    at_time: int,
) -> FiredEvent:
    action = _action(event)
    narrative = _handler(event.action_type).execute(
        session, ctx, campaign_id, event, action, at_time
    )
    return FiredEvent(
        scheduled_event_id=event.id,
        title=event.title,
        at_time=at_time,
        at_label=cal.format(at_time)["label"],
        narrative=narrative,
    )


def fire_due_events(
    session: Session,
    ctx: CommandContext,
    cal: CalendarMath,
    campaign: Campaign,
    to_time: int,
) -> list[FiredEvent]:
    """Fire every pending event with fire_at <= to_time, in chronological order."""
    fired: list[FiredEvent] = []
    guard = 0
    seconds_per_day = cal.seconds_per_day

    # Compile recurring rules into the queue first, so their occurrences take part in the
    # same ordered pass as the events already sitting in it.
    for handler in _MATERIALIZERS:
        handler.materialize(session, campaign, to_time)

    while True:
        due = session.scalars(
            select(ScheduledEvent)
            .where(
                ScheduledEvent.campaign_id == campaign.id,
                ScheduledEvent.status == "pending",
                ScheduledEvent.fire_at_game <= to_time,
            )
            .order_by(ScheduledEvent.fire_at_game, ScheduledEvent.id)
            .limit(1)
        ).first()
        if due is None:
            break

        guard += 1
        if guard > FIRING_CEILING:
            raise RunawayGuard(
                f"scheduled-event firing exceeded {FIRING_CEILING}; check recurrences"
            )

        at_time = due.fire_at_game
        campaign.clock_time_game = at_time  # time flows through the event
        fired.append(_execute(session, ctx, cal, campaign.id, due, at_time))

        if due.recurrence_days:
            due.fire_at_game = at_time + due.recurrence_days * seconds_per_day
        else:
            due.status = "fired"
        session.flush()

    return fired


def preview_due_events(
    session: Session, cal: CalendarMath, campaign: Campaign, to_time: int
) -> list[FiredEvent]:
    """Read-only: what *would* fire in (now, to_time], expanding recurrences. No writes."""
    seconds_per_day = cal.seconds_per_day
    occurrences: list[tuple[int, ScheduledEvent]] = []
    for event in list_events(session, campaign.id, status="pending"):
        t = event.fire_at_game
        steps = 0
        while t <= to_time:
            occurrences.append((t, event))
            if not event.recurrence_days:
                break
            t += event.recurrence_days * seconds_per_day
            steps += 1
            if steps > FIRING_CEILING:
                break
    occurrences.sort(key=lambda pair: (pair[0], pair[1].id))

    preview: list[FiredEvent] = []
    for at_time, event in occurrences[:FIRING_CEILING]:
        preview.append(
            FiredEvent(
                scheduled_event_id=event.id,
                title=event.title,
                at_time=at_time,
                at_label=cal.format(at_time)["label"],
                narrative=_handler(event.action_type).describe(event, _action(event)),
            )
        )

    # Rules that have not been compiled into the queue yet would still fire en route, so the
    # dry run asks each materializer what it *would* produce (docs/07 §9.5). Still no writes.
    for handler in _MATERIALIZERS:
        for at_time, narrative in handler.preview(session, campaign, to_time):
            preview.append(
                FiredEvent(
                    scheduled_event_id=None, title="Itinerary", at_time=at_time,
                    at_label=cal.format(at_time)["label"], narrative=narrative,
                )
            )

    preview.sort(key=lambda f: f.at_time)
    return preview[:FIRING_CEILING]
