"""Sprint 14 — live session dashboard composite read (FR-14, the MVP gate)."""

from __future__ import annotations

from fastapi.testclient import TestClient

_AB = {"str": 10, "dex": 14, "con": 14, "int": 8, "wis": 12, "cha": 10}


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def test_dashboard_composes_the_table(client: TestClient) -> None:
    cid = _demo(client)
    tavern = client.post(f"/api/v1/campaigns/{cid}/entities",
                         json={"entity_type": "location", "name": "Barrow Tavern"}).json()["id"]
    barkeep = client.post(f"/api/v1/campaigns/{cid}/entities",
                          json={"entity_type": "npc", "name": "Old Halda"}).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/entities/{barkeep}/links",
                json={"to_entity": tavern, "link_type_id": "located_at"})
    client.post(f"/api/v1/campaigns/{cid}/entities",
                json={"entity_type": "quest", "name": "Find the Amulet"})
    client.post(f"/api/v1/campaigns/{cid}/notes", json={"text": "The party arrives at dusk."})

    # Point the dashboard at the tavern → NPCs-here should surface the barkeep.
    dash = client.put(f"/api/v1/campaigns/{cid}/views/dashboard/location",
                      json={"entity_id": tavern}).json()
    assert dash["current_location"]["name"] == "Barrow Tavern"
    assert any(n["name"] == "Old Halda" for n in dash["npcs_here"])
    assert any(q["name"] == "Find the Amulet" for q in dash["active_quests"])
    assert any(e["event_type"] == "note_captured" for e in dash["notes"])
    assert dash["party"]["id"]  # party is auto-created
    assert dash["clock"]["formatted"]["seconds"] is not None
    assert dash["active_combat"] is None


def test_dashboard_get_matches_setters(client: TestClient) -> None:
    cid = _demo(client)
    npc = client.post(f"/api/v1/campaigns/{cid}/entities",
                      json={"entity_type": "npc", "name": "Pinned Seer"}).json()["id"]

    client.put(f"/api/v1/campaigns/{cid}/views/dashboard/pins",
               json={"entity_id": npc, "pinned": True})
    dash = client.get(f"/api/v1/campaigns/{cid}/views/dashboard").json()
    assert any(p["name"] == "Pinned Seer" for p in dash["pinned"])

    # Unpin removes it.
    client.put(f"/api/v1/campaigns/{cid}/views/dashboard/pins",
               json={"entity_id": npc, "pinned": False})
    dash = client.get(f"/api/v1/campaigns/{cid}/views/dashboard").json()
    assert not any(p["name"] == "Pinned Seer" for p in dash["pinned"])


def test_dashboard_shows_active_combat(client: TestClient) -> None:
    cid = _demo(client)
    run = client.post(f"/api/v1/campaigns/{cid}/combats", json={"encounter_id": None})
    assert run.status_code == 201
    dash = client.get(f"/api/v1/campaigns/{cid}/views/dashboard").json()
    assert dash["active_combat"] is not None
    assert dash["active_combat"]["run_id"] == run.json()["run_id"]
    # Combat pauses the realtime clock (6s/round takes over).
    assert dash["clock"]["realtime_paused"] is True


def test_set_location_rejects_unknown_entity(client: TestClient) -> None:
    cid = _demo(client)
    resp = client.put(f"/api/v1/campaigns/{cid}/views/dashboard/location",
                      json={"entity_id": "does-not-exist"})
    assert resp.status_code == 404
