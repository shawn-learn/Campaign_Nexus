"""Sprint 2: campaign create, scoping, entity CRUD/soft-delete/restore, tags — all audited."""

from __future__ import annotations

from fastapi.testclient import TestClient


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
