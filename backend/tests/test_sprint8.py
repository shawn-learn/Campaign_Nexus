"""Sprint 8: timeline projection, sessions (live stamping), notes, rebuild consistency."""

from __future__ import annotations

from app.core.db import SessionLocal
from app.modules.chronicle.models import TimelineEntry
from fastapi.testclient import TestClient
from scripts.rebuild_projections import rebuild
from sqlalchemy import select

DAY = 24 * 3600


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _entity(client: TestClient, cid: str, name: str, etype: str = "npc") -> str:
    return client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": etype, "name": name}
    ).json()["id"]


def _timeline(client: TestClient, cid: str, **params):
    return client.get(f"/api/v1/campaigns/{cid}/timeline", params=params).json()


def test_scheduled_world_event_projects_to_timeline(client: TestClient) -> None:
    cid = _demo(client)
    client.post(
        f"/api/v1/campaigns/{cid}/scheduled-events",
        json={"title": "Festival", "fire_at_game": DAY, "action_type": "narrate",
              "action_json": {"text": "The Feast of Lanterns begins."}},
    )
    client.post(f"/api/v1/campaigns/{cid}/clock/advance", json={"days": 2})
    tl = _timeline(client, cid)
    assert any(e["title"] == "The Feast of Lanterns begins." for e in tl)
    # Wiki audit noise does not clutter the timeline.
    assert all("Created" not in e["title"] for e in tl)


def test_manual_lore_entry_with_entity_filter(client: TestClient) -> None:
    cid = _demo(client)
    king = _entity(client, cid, "Old King Aldric")
    client.post(
        f"/api/v1/campaigns/{cid}/timeline/manual",
        json={"title": "The Sundering", "occurred_at_game": -365 * DAY,  # pre-campaign lore
              "significance": 4, "entity_ids": [king]},
    )
    # Filter by entity returns the linked lore entry.
    hits = _timeline(client, cid, entity_id=king)
    assert [e["title"] for e in hits] == ["The Sundering"]
    assert hits[0]["event_id"] is None  # manual entry


def test_live_session_stamps_events_and_autolinks(client: TestClient) -> None:
    cid = _demo(client)
    npc = _entity(client, cid, "Serah Voss")
    sess = client.post(f"/api/v1/campaigns/{cid}/sessions", json={}).json()
    client.post(f"/api/v1/campaigns/{cid}/sessions/{sess['id']}/start")

    # Events during the live session get stamped with it.
    client.post(f"/api/v1/campaigns/{cid}/clock/advance", json={"hours": 8, "reason": "long rest"})
    client.post(
        f"/api/v1/campaigns/{cid}/notes",
        json={"text": "The party bargained with Serah.", "entity_ids": [npc]},
    )
    client.post(f"/api/v1/campaigns/{cid}/sessions/{sess['id']}/end")

    detail = client.get(f"/api/v1/campaigns/{cid}/sessions/{sess['id']}").json()
    kinds = [e["event_type"] for e in detail["events"]]
    assert "session_started" in kinds and "time_advanced" in kinds
    assert "note_captured" in kinds and "session_ended" in kinds
    # Auto-linked entities (subjects of the session's events).
    assert [e["name"] for e in detail["entities"]] == ["Serah Voss"]

    # The timeline filters by that session.
    tl = _timeline(client, cid, session_id=sess["id"])
    assert any(e["title"] == "The party bargained with Serah." for e in tl)


def test_only_one_live_session(client: TestClient) -> None:
    cid = _demo(client)
    a = client.post(f"/api/v1/campaigns/{cid}/sessions", json={}).json()
    b = client.post(f"/api/v1/campaigns/{cid}/sessions", json={}).json()
    client.post(f"/api/v1/campaigns/{cid}/sessions/{a['id']}/start")
    resp = client.post(f"/api/v1/campaigns/{cid}/sessions/{b['id']}/start")
    assert resp.status_code == 409


def test_date_range_filter(client: TestClient) -> None:
    cid = _demo(client)
    client.post(
        f"/api/v1/campaigns/{cid}/timeline/manual",
        json={"title": "Early", "occurred_at_game": 5 * DAY},
    )
    client.post(
        f"/api/v1/campaigns/{cid}/timeline/manual",
        json={"title": "Late", "occurred_at_game": 50 * DAY},
    )
    hits = _timeline(client, cid, from_game=10 * DAY, to_game=100 * DAY)
    assert [e["title"] for e in hits] == ["Late"]


def test_rebuild_projections_matches_incremental(client: TestClient) -> None:
    """Consistency oracle (§8.4): rebuild from the event log ≡ incremental projection."""
    cid = _demo(client)
    # Generate a variety of projected events.
    client.post(
        f"/api/v1/campaigns/{cid}/scheduled-events",
        json={"title": "Market", "fire_at_game": 7 * DAY, "action_type": "narrate",
              "action_json": {"text": "Market day."}, "recurrence_days": 7},
    )
    client.post(f"/api/v1/campaigns/{cid}/clock/advance", json={"days": 30})
    sess = client.post(f"/api/v1/campaigns/{cid}/sessions", json={}).json()
    client.post(f"/api/v1/campaigns/{cid}/sessions/{sess['id']}/start")
    client.post(f"/api/v1/campaigns/{cid}/notes", json={"text": "A note."})
    client.post(f"/api/v1/campaigns/{cid}/sessions/{sess['id']}/end")

    before = _projected_snapshot(cid)
    assert before  # non-empty

    with SessionLocal() as db:
        rebuild(db, cid)

    after = _projected_snapshot(cid)
    assert after == before


def _projected_snapshot(campaign_id: str) -> list[tuple]:
    """Order-independent snapshot of event-derived timeline entries (ignores random ids)."""
    with SessionLocal() as db:
        rows = db.scalars(
            select(TimelineEntry).where(
                TimelineEntry.campaign_id == campaign_id,
                TimelineEntry.event_id.is_not(None),
            )
        )
        return sorted(
            (r.event_id, r.occurred_at_game, r.title, r.significance, r.session_id) for r in rows
        )
