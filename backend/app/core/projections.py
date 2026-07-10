"""Synchronous projection registry (ADR-004, §8.1 step 5).

Projectors run *inside* the command transaction, right after the domain events are
appended and before commit — so a projection (e.g. a timeline entry) can never disagree
with the events it is derived from. Feature modules register projectors at import time;
core never imports them (dependency direction preserved).

The same projectors are replayed by ``scripts.rebuild_projections`` to re-derive every
projection from the event log — the recovery hatch and the consistency oracle in tests.
A replay must start from a clean slate, so a module that owns projected state also
registers a **reset** that truncates it (core stays ignorant of which tables those are).
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.event_bus import EventRecord

Projector = Callable[[Session, EventRecord], None]
#: ``(session, campaign_id | None)`` — clear this module's projected rows before a replay.
Resetter = Callable[[Session, str | None], None]

_projectors: list[Projector] = []
_resetters: list[Resetter] = []


def register_projector(projector: Projector) -> None:
    if projector not in _projectors:
        _projectors.append(projector)


def register_reset(resetter: Resetter) -> None:
    if resetter not in _resetters:
        _resetters.append(resetter)


def run_projectors(session: Session, events: list[EventRecord]) -> None:
    for event in events:
        for projector in _projectors:
            projector(session, event)


def reset_projections(session: Session, campaign_id: str | None = None) -> None:
    """Truncate every registered projection (scoped to one campaign when given)."""
    for resetter in _resetters:
        resetter(session, campaign_id)
    session.flush()
