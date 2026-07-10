"""Rebuild all projections by replaying the domain event log (docs/06, §8.4).

    python -m scripts.rebuild_projections [campaign_id]

Truncates the projection tables and replays every domain event (in seq order) through the
registered projectors. This is the recovery hatch after a projector bug/schema change, and
the consistency oracle used in tests (incremental result must equal a rebuild).

Projection tables are truncated by the modules that own them (each registers a reset with
``app.core.projections``), then every event is folded back through the projectors. Projected
timeline entries are rebuilt; manual entries (event_id NULL) are GM-authored and preserved.
"""

from __future__ import annotations

import json
import sys

from app.core.db import SessionLocal
from app.core.domain_event import DomainEvent
from app.core.event_bus import EventRecord
from app.core.projections import reset_projections, run_projectors
from app.db_metadata import metadata  # noqa: F401  (imports models + registers projectors)
from sqlalchemy import select
from sqlalchemy.orm import Session


def _to_record(row: DomainEvent) -> EventRecord:
    return EventRecord(
        id=row.id,
        campaign_id=row.campaign_id,
        seq=row.seq,
        event_type=row.event_type,
        occurred_at_game=row.occurred_at_game,
        recorded_at_real=row.recorded_at_real,
        session_id=row.session_id,
        actor=row.actor,
        payload=json.loads(row.payload_json),
        narrative_text=row.narrative_text,
        subject_entity_ids=tuple(json.loads(row.subject_entity_ids_json)),
    )


def rebuild(db: Session, campaign_id: str | None = None) -> int:
    """Rebuild every projection for one campaign (or all). Returns the event count."""
    event_stmt = select(DomainEvent).order_by(DomainEvent.campaign_id, DomainEvent.seq)
    if campaign_id:
        event_stmt = event_stmt.where(DomainEvent.campaign_id == campaign_id)

    # Each module truncates the projections it owns (core doesn't know their tables).
    reset_projections(db, campaign_id)

    events = list(db.scalars(event_stmt))
    run_projectors(db, [_to_record(e) for e in events])
    db.commit()
    return len(events)


def main() -> None:
    campaign_id = sys.argv[1] if len(sys.argv) > 1 else None
    with SessionLocal() as db:
        count = rebuild(db, campaign_id)
    scope = campaign_id or "all campaigns"
    print(f"replayed {count} events for {scope}")


if __name__ == "__main__":
    main()
