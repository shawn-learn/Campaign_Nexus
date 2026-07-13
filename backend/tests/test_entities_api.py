"""Sprint 1 exit criterion: POST /entities creates an entity and an event atomically."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _demo_campaign_id(client: TestClient) -> str:
    resp = client.get("/api/v1/campaigns")
    assert resp.status_code == 200
    campaigns = resp.json()
    assert campaigns, "bootstrap should have created the demo campaign"
    return campaigns[0]["id"]


def test_health(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_post_entity_creates_entity_and_event(client: TestClient) -> None:
    campaign_id = _demo_campaign_id(client)

    resp = client.post(
        f"/api/v1/campaigns/{campaign_id}/entities",
        json={"entity_type": "note", "name": "Serah Voss"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Serah Voss"
    assert body["slug"] == "serah-voss"

    # The atomic event landed and is readable.
    events = client.get(f"/api/v1/campaigns/{campaign_id}/events").json()
    assert len(events) == 1
    assert events[0]["event_type"] == "entity_created"
    assert events[0]["payload"]["name"] == "Serah Voss"


def test_slug_uniqueness(client: TestClient) -> None:
    campaign_id = _demo_campaign_id(client)
    url = f"/api/v1/campaigns/{campaign_id}/entities"
    first = client.post(url, json={"entity_type": "note", "name": "Tavern"}).json()
    second = client.post(url, json={"entity_type": "note", "name": "Tavern"}).json()
    assert first["slug"] == "tavern"
    assert second["slug"] == "tavern-2"


def test_unknown_entity_type_rejected(client: TestClient) -> None:
    campaign_id = _demo_campaign_id(client)
    resp = client.post(
        f"/api/v1/campaigns/{campaign_id}/entities",
        json={"entity_type": "dragon_hoard", "name": "x"},
    )
    assert resp.status_code == 422


def _names(client: TestClient, cid: str, **params: object) -> list[str]:
    resp = client.get(f"/api/v1/campaigns/{cid}/entities", params=params)
    assert resp.status_code == 200, resp.text
    return [e["name"] for e in resp.json()]


def test_entities_name_sort_and_fallback(client: TestClient) -> None:
    cid = _demo_campaign_id(client)
    url = f"/api/v1/campaigns/{cid}/entities"
    for name in ("Banshee", "Aboleth", "Cthulhu"):
        client.post(url, json={"entity_type": "note", "name": name})

    assert _names(client, cid, sort="name") == ["Aboleth", "Banshee", "Cthulhu"]
    assert _names(client, cid, sort="-name") == ["Cthulhu", "Banshee", "Aboleth"]
    # An unknown sort value falls back to the default (no error, all rows returned).
    assert set(_names(client, cid, sort="bogus")) == {"Aboleth", "Banshee", "Cthulhu"}


def test_entities_q_matches_name_and_summary(client: TestClient) -> None:
    cid = _demo_campaign_id(client)
    url = f"/api/v1/campaigns/{cid}/entities"
    client.post(url, json={"entity_type": "npc", "name": "Ismark", "summary": "the Lesser"})
    client.post(
        url, json={"entity_type": "npc", "name": "Ireena", "summary": "burgomaster's daughter"}
    )

    # Matches a name...
    assert _names(client, cid, q="ismark") == ["Ismark"]
    # ...and a summary the name doesn't contain.
    assert _names(client, cid, q="burgomaster") == ["Ireena"]
