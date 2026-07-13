"""Service-level sort ordering for the browse hub. Timestamps are set explicitly because
the OS wall clock is too coarse (~15 ms on Windows) to distinguish rows created back-to-back
through the API, which would make created/updated order nondeterministic."""

from __future__ import annotations

from app.modules.campaign import service as campaign_service
from app.modules.wiki import service as wiki_service
from app.modules.wiki.models import Entity
from sqlalchemy.orm import Session


def _entity(
    db: Session, campaign_id: str, user_id: str, name: str, created: str, updated: str
) -> None:
    db.add(
        Entity(
            id=name.lower(), campaign_id=campaign_id, entity_type="note", name=name,
            slug=name.lower(), created_by=user_id,
            created_at_real=created, updated_at_real=updated,
        )
    )


def test_list_entities_created_and_updated_sorts(db: Session) -> None:
    cid = campaign_service.ensure_bootstrap(db).id
    uid = campaign_service.get_local_user_id(db)
    # Created A→B→C; but B was edited most recently.
    _entity(db, cid, uid, "A", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    _entity(db, cid, uid, "B", "2026-01-02T00:00:00Z", "2026-03-01T00:00:00Z")
    _entity(db, cid, uid, "C", "2026-01-03T00:00:00Z", "2026-01-03T00:00:00Z")
    db.commit()

    def names(sort: str | None) -> list[str]:
        return [e.name for e in wiki_service.list_entities(db, cid, sort=sort)]

    assert names(None) == ["C", "B", "A"]        # default: newest created first
    assert names("created") == ["C", "B", "A"]
    assert names("-created") == ["A", "B", "C"]
    assert names("updated") == ["B", "C", "A"]   # B edited last → first
    assert names("-updated") == ["A", "C", "B"]
    assert names("name") == ["A", "B", "C"]
    assert names("-name") == ["C", "B", "A"]
