"""The command pipeline's core guarantee: state + events commit atomically (ADR-004)."""

from __future__ import annotations

import pytest
from app.core.domain_event import DomainEvent
from app.core.pipeline import command_tx
from app.modules.campaign import service as campaign_service
from app.modules.wiki.models import Entity
from app.modules.wiki.schemas import EntityCreate
from app.modules.wiki.service import create_entity
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _campaign(db: Session) -> str:
    return campaign_service.ensure_bootstrap(db).id


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_create_entity_commits_entity_and_event(db: Session) -> None:
    campaign_id = _campaign(db)
    user_id = campaign_service.get_local_user_id(db)

    entity = create_entity(
        db,
        campaign_id,
        data=EntityCreate(entity_type="note", name="First Note"),
        created_by=user_id,
    )

    assert _count(db, Entity) == 1
    events = list(db.scalars(select(DomainEvent).where(DomainEvent.campaign_id == campaign_id)))
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "entity_created"
    assert event.seq == 1
    assert event.payload_json and entity.id in event.payload_json
    assert "First Note" in event.narrative_text


def test_seq_is_monotonic_per_campaign(db: Session) -> None:
    campaign_id = _campaign(db)
    user_id = campaign_service.get_local_user_id(db)
    for name in ("A", "B", "C"):
        create_entity(db, campaign_id, data=EntityCreate(entity_type="note", name=name),
                      created_by=user_id)
    seqs = sorted(db.scalars(select(DomainEvent.seq)))
    assert seqs == [1, 2, 3]


def test_failure_rolls_back_state_and_event(db: Session) -> None:
    """If the command body raises, neither state nor event is persisted."""
    campaign_id = _campaign(db)

    with pytest.raises(RuntimeError), command_tx(db, campaign_id, actor="gm") as ctx:
        db.add(
            Entity(
                id="00000000-0000-7000-8000-000000000000",
                campaign_id=campaign_id,
                entity_type="note",
                name="Doomed",
                slug="doomed",
                created_by=campaign_service.get_local_user_id(db),
                created_at_real="2026-01-01T00:00:00+00:00",
                updated_at_real="2026-01-01T00:00:00+00:00",
            )
        )
        ctx.emit("entity_created", payload={}, narrative="should not persist")
        raise RuntimeError("boom")

    assert _count(db, Entity) == 0
    assert _count(db, DomainEvent) == 0
