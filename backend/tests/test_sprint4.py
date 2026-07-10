"""Sprint 4: explicit typed relations, the 'within' hierarchy, cycle guard, breadcrumbs."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _entity(client: TestClient, cid: str, name: str, etype: str) -> str:
    return client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": etype, "name": name}
    ).json()["id"]


def _link(client: TestClient, cid: str, frm: str, to: str, type_id: str):
    return client.post(
        f"/api/v1/campaigns/{cid}/entities/{frm}/links",
        json={"to_entity": to, "link_type_id": type_id},
    )


def test_builtin_link_types_present(client: TestClient) -> None:
    cid = _demo(client)
    types = {t["id"] for t in client.get(f"/api/v1/campaigns/{cid}/link-types").json()}
    assert {"within", "located_at", "member_of", "mentions"} <= types


def test_explicit_link_creates_relation_and_backlink(client: TestClient) -> None:
    cid = _demo(client)
    npc = _entity(client, cid, "Serah Voss", "npc")
    tavern = _entity(client, cid, "Barrow Tavern", "location")

    detail = _link(client, cid, npc, tavern, "located_at").json()
    edge = next(o for o in detail["outbound"] if o["entity_id"] == tavern)
    assert edge["label"] == "located at" and edge["source"] == "explicit"

    # The tavern shows the NPC under its inverse label.
    tavern_detail = client.get(f"/api/v1/campaigns/{cid}/entities/{tavern}").json()
    back = next(b for b in tavern_detail["backlinks"] if b["entity_id"] == npc)
    assert back["label"] == "location of"


def test_within_hierarchy_breadcrumb(client: TestClient) -> None:
    cid = _demo(client)
    region = _entity(client, cid, "The Reach", "location")
    city = _entity(client, cid, "Duskmere", "location")
    tavern = _entity(client, cid, "Barrow Tavern", "location")

    assert _link(client, cid, city, region, "within").status_code == 200
    assert _link(client, cid, tavern, city, "within").status_code == 200

    detail = client.get(f"/api/v1/campaigns/{cid}/entities/{tavern}").json()
    # Breadcrumb is root → parent order.
    assert [a["name"] for a in detail["ancestors"]] == ["The Reach", "Duskmere"]


def test_within_cycle_is_rejected(client: TestClient) -> None:
    cid = _demo(client)
    a = _entity(client, cid, "Region A", "location")
    b = _entity(client, cid, "City B", "location")
    assert _link(client, cid, b, a, "within").status_code == 200  # B within A

    # A within B would close a cycle → 409 with a clear message.
    resp = _link(client, cid, a, b, "within")
    assert resp.status_code == 409
    assert "cycle" in resp.json()["detail"].lower()


def test_self_link_rejected(client: TestClient) -> None:
    cid = _demo(client)
    a = _entity(client, cid, "Lonely", "location")
    assert _link(client, cid, a, a, "within").status_code == 422


def test_delete_link_removes_relation(client: TestClient) -> None:
    cid = _demo(client)
    npc = _entity(client, cid, "Guard", "npc")
    faction = _entity(client, cid, "City Watch", "faction")
    detail = _link(client, cid, npc, faction, "member_of").json()
    link_id = detail["outbound"][0]["link_id"]

    after = client.delete(f"/api/v1/campaigns/{cid}/links/{link_id}").json()
    assert after["outbound"] == []
    types = [e["event_type"] for e in client.get(f"/api/v1/campaigns/{cid}/events").json()]
    assert "link_added" in types and "link_removed" in types
