"""The command pipeline — the *only* write path in the system (docs/06, §8.1).

Every mutation runs inside ``command_tx``: mutate state tables, append one or more
domain events, and commit them in a single ACID transaction (NFR-2.1). After commit,
the events are published on the in-process bus for reactive subscribers.

Usage::

    with command_tx(session, campaign_id, actor="gm") as ctx:
        session.add(entity)                       # 1. mutate state
        ctx.emit("entity_created", payload={...},  # 2. record the fact
                 narrative="Created NPC 'Serah Voss'.")
    # commit + post-commit publish happen on clean exit
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import now_real_iso
from app.core.domain_event import DomainEvent
from app.core.event_bus import EventRecord, event_bus
from app.core.ids import new_id
from app.core.projections import run_projectors


@dataclass
class _PendingEvent:
    event_type: str
    payload: dict[str, object]
    narrative: str
    occurred_at_game: int | None
    session_id: str | None
    subject_entity_ids: tuple[str, ...]


@dataclass
class CommandContext:
    """Handed to command bodies; accumulates events to append atomically."""

    session: Session
    campaign_id: str
    actor: str
    _pending: list[_PendingEvent] = field(default_factory=list)

    def emit(
        self,
        event_type: str,
        *,
        payload: dict[str, object],
        narrative: str,
        occurred_at_game: int | None = None,
        session_id: str | None = None,
        subject_entity_ids: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        """Record a domain event to be appended when the command commits.

        ``occurred_at_game`` defaults to the campaign's current clock (FR-5.7); pass
        an explicit value for backdated or scheduled-in-the-past facts.
        ``subject_entity_ids`` are the entities this event is about (timeline/session
        filtering + auto-linking).
        """
        self._pending.append(
            _PendingEvent(
                event_type, payload, narrative, occurred_at_game, session_id,
                tuple(subject_entity_ids or ()),
            )
        )


def _current_game_time(session: Session, campaign_id: str) -> int:
    """Read the campaign clock without importing the campaign module (keeps core a leaf)."""
    result = session.execute(
        text("SELECT clock_time_game FROM campaign WHERE id = :cid"),
        {"cid": campaign_id},
    ).scalar_one_or_none()
    return int(result) if result is not None else 0


def _next_seq(session: Session, campaign_id: str) -> int:
    """Per-campaign monotonic sequence (single-writer model makes max+1 safe)."""
    current = session.execute(
        text("SELECT COALESCE(MAX(seq), 0) FROM domain_event WHERE campaign_id = :cid"),
        {"cid": campaign_id},
    ).scalar_one()
    return int(current) + 1


def _current_session_id(session: Session, campaign_id: str) -> str | None:
    """The live session, if any — events emitted during it are auto-stamped (FR-9.2)."""
    return session.execute(
        text("SELECT current_session_id FROM campaign WHERE id = :cid"),
        {"cid": campaign_id},
    ).scalar_one_or_none()


@contextmanager
def command_tx(session: Session, campaign_id: str, *, actor: str) -> Iterator[CommandContext]:
    ctx = CommandContext(session=session, campaign_id=campaign_id, actor=actor)
    try:
        yield ctx

        session.flush()  # surface state-mutation errors before we append events
        game_time = _current_game_time(session, campaign_id)
        live_session = _current_session_id(session, campaign_id)
        seq = _next_seq(session, campaign_id)
        recorded_at = now_real_iso()

        committed: list[EventRecord] = []
        for pending in ctx._pending:
            event_id = new_id()
            occurred = (
                pending.occurred_at_game
                if pending.occurred_at_game is not None
                else game_time
            )
            session_id = pending.session_id if pending.session_id is not None else live_session
            session.add(
                DomainEvent(
                    id=event_id,
                    campaign_id=campaign_id,
                    seq=seq,
                    event_type=pending.event_type,
                    occurred_at_game=occurred,
                    recorded_at_real=recorded_at,
                    session_id=session_id,
                    actor=actor,
                    payload_json=json.dumps(pending.payload),
                    narrative_text=pending.narrative,
                    subject_entity_ids_json=json.dumps(list(pending.subject_entity_ids)),
                )
            )
            committed.append(
                EventRecord(
                    id=event_id,
                    campaign_id=campaign_id,
                    seq=seq,
                    event_type=pending.event_type,
                    occurred_at_game=occurred,
                    recorded_at_real=recorded_at,
                    session_id=session_id,
                    actor=actor,
                    payload=pending.payload,
                    narrative_text=pending.narrative,
                    subject_entity_ids=pending.subject_entity_ids,
                )
            )
            seq += 1

        # Synchronous projections run in-transaction (ADR-004): flush events first so
        # projection rows can FK-reference them, then project, then commit atomically.
        session.flush()
        run_projectors(session, committed)
        session.commit()
    except Exception:
        session.rollback()
        raise

    # Post-commit: subscribers observe only durable facts.
    event_bus.publish(committed)
