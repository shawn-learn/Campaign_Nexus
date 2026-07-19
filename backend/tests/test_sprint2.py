"""Sprint 2: campaign create, scoping, entity CRUD/soft-delete/restore, tags — all audited."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _event_types(client: TestClient, campaign_id: str) -> list[str]:
    events = client.get(f"/api/v1/campaigns/{campaign_id}/events").json()
    return [e["event_type"] for e in events]


def test_create_campaign_emits_event_and_owner(client: TestClient) -> None:
    resp = client.post("/api/v1/campaigns", json={"name": "Sword Coast"})
    assert resp.status_code == 201, resp.text
    cid = resp.json()["id"]

    # The new campaign is owned by the local user (scoped reads succeed) and audited.
    assert client.get(f"/api/v1/campaigns/{cid}/entities").status_code == 200
    assert _event_types(client, cid) == ["campaign_created"]


def test_unknown_rule_system_rejected(client: TestClient) -> None:
    resp = client.post("/api/v1/campaigns", json={"name": "X", "rule_system_id": "pathfinder"})
    assert resp.status_code == 422


def test_scoping_unknown_campaign_is_404(client: TestClient) -> None:
    missing = "00000000-0000-7000-8000-000000000000"
    assert client.get(f"/api/v1/campaigns/{missing}/entities").status_code == 404
    assert (
        client.post(f"/api/v1/campaigns/{missing}/entities",
                    json={"entity_type": "note", "name": "x"}).status_code
        == 404
    )


def test_rename_and_summary_update_audited(client: TestClient) -> None:
    cid = _demo(client)
    eid = client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": "npc", "name": "Bob"}
    ).json()["id"]

    resp = client.patch(
        f"/api/v1/campaigns/{cid}/entities/{eid}",
        json={"name": "Bthorin", "summary": "A dwarf", "summary_set": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Bthorin"
    assert body["summary"] == "A dwarf"
    # Rename does not change the (stable) slug.
    assert body["slug"] == "bob"

    assert "entity_updated" in _event_types(client, cid)


def test_soft_delete_and_restore(client: TestClient) -> None:
    cid = _demo(client)
    eid = client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": "location", "name": "Keep"}
    ).json()["id"]

    # Delete: hidden from default list, visible with include_deleted.
    assert client.delete(f"/api/v1/campaigns/{cid}/entities/{eid}").json()["deleted"] is True
    listed = client.get(f"/api/v1/campaigns/{cid}/entities").json()
    assert eid not in [e["id"] for e in listed]
    with_deleted = client.get(
        f"/api/v1/campaigns/{cid}/entities", params={"include_deleted": "true"}
    ).json()
    assert eid in [e["id"] for e in with_deleted]

    # Double-delete is a conflict.
    assert client.delete(f"/api/v1/campaigns/{cid}/entities/{eid}").status_code == 409

    # Restore brings it back.
    assert client.post(f"/api/v1/campaigns/{cid}/entities/{eid}/restore").json()["deleted"] is False
    assert eid in [e["id"] for e in client.get(f"/api/v1/campaigns/{cid}/entities").json()]

    types = _event_types(client, cid)
    assert "entity_deleted" in types and "entity_restored" in types


def test_purge_removes_only_soft_deleted(client: TestClient) -> None:
    cid = _demo(client)
    keep = client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": "location", "name": "Keep"}
    ).json()["id"]
    doomed = client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": "note", "name": "Scratch"}
    ).json()["id"]
    client.delete(f"/api/v1/campaigns/{cid}/entities/{doomed}")

    resp = client.post(f"/api/v1/campaigns/{cid}/entities/purge")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 1
    assert [e["name"] for e in body["entities"]] == ["Scratch"]

    # Gone for good — not even include_deleted finds it. The live entity is untouched.
    with_deleted = client.get(
        f"/api/v1/campaigns/{cid}/entities", params={"include_deleted": "true"}
    ).json()
    ids = [e["id"] for e in with_deleted]
    assert doomed not in ids
    assert keep in ids
    assert client.get(f"/api/v1/campaigns/{cid}/entities/{doomed}").status_code == 404
    assert "entities_purged" in _event_types(client, cid)


def test_purge_with_nothing_deleted_is_a_no_op(client: TestClient) -> None:
    cid = _demo(client)
    resp = client.post(f"/api/v1/campaigns/{cid}/entities/purge")
    assert resp.status_code == 200
    assert resp.json() == {"count": 0, "entities": []}
    # A no-op must not litter the audit log.
    assert "entities_purged" not in _event_types(client, cid)


def test_soft_deleted_npc_drops_out_of_the_npc_list(client: TestClient) -> None:
    """Soft delete leaves the Npc row behind; the list must still hide it."""
    cid = _demo(client)
    eid = client.post(
        f"/api/v1/campaigns/{cid}/npcs", json={"name": "Doomed Baron"}
    ).json()["entity_id"]
    assert eid in [n["entity_id"] for n in client.get(f"/api/v1/campaigns/{cid}/npcs").json()]

    client.delete(f"/api/v1/campaigns/{cid}/entities/{eid}")
    assert eid not in [n["entity_id"] for n in client.get(f"/api/v1/campaigns/{cid}/npcs").json()]

    # ...but include_deleted still reaches it, flagged, so it can be found and restored.
    listed = client.get(
        f"/api/v1/campaigns/{cid}/npcs", params={"include_deleted": "true"}
    ).json()
    match = [n for n in listed if n["entity_id"] == eid]
    assert match and match[0]["deleted"] is True

    client.post(f"/api/v1/campaigns/{cid}/entities/{eid}/restore")
    back = client.get(f"/api/v1/campaigns/{cid}/npcs").json()
    assert next(n for n in back if n["entity_id"] == eid)["deleted"] is False


def test_projection_rebuild_survives_a_purge(client: TestClient, db: Session) -> None:
    """Events keep naming a purged entity; replaying them must not blow up on the dead id."""
    from scripts.rebuild_projections import rebuild

    cid = _demo(client)
    eid = client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": "npc", "name": "Ghost"}
    ).json()["id"]
    client.post(
        f"/api/v1/campaigns/{cid}/notes",
        json={"text": "Ghost was here", "entity_ids": [eid]},
    )
    client.delete(f"/api/v1/campaigns/{cid}/entities/{eid}")
    assert client.post(f"/api/v1/campaigns/{cid}/entities/purge").json()["count"] == 1

    # Without the guard in chronicle.projectors this raises IntegrityError on the dead id.
    assert rebuild(db, cid) > 0


def test_tagging_and_filtering(client: TestClient) -> None:
    cid = _demo(client)
    a = client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": "npc", "name": "Ally"}
    ).json()["id"]
    b = client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": "npc", "name": "Foe"}
    ).json()["id"]

    tagged = client.post(
        f"/api/v1/campaigns/{cid}/entities/{a}/tags", json={"name": "villain"}
    ).json()
    assert [t["name"] for t in tagged["tags"]] == ["villain"]
    tag_id = tagged["tags"][0]["id"]

    # Filter by tag returns only the tagged entity.
    filtered = client.get(
        f"/api/v1/campaigns/{cid}/entities", params={"tag_id": tag_id}
    ).json()
    assert [e["id"] for e in filtered] == [a]

    # Untag removes it.
    untagged = client.delete(
        f"/api/v1/campaigns/{cid}/entities/{a}/tags/{tag_id}"
    ).json()
    assert untagged["tags"] == []
    assert b not in [e["id"] for e in filtered]

    types = _event_types(client, cid)
    assert "entity_tagged" in types and "entity_untagged" in types
