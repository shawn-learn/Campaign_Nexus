from __future__ import annotations

from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _entity(client: TestClient, cid: str, entity_type: str, name: str) -> str:
    resp = client.post(
        f"/api/v1/campaigns/{cid}/entities", json={"entity_type": entity_type, "name": name}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _make_equipment(client: TestClient, cid: str, **overrides: object) -> dict:
    body = {"name": "Longsword", "item_type": "mundane", "value_gp": "15 gp", "weight_lb": 3.0}
    body.update(overrides)
    resp = client.post(f"/api/v1/campaigns/{cid}/equipment", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_item(client: TestClient, cid: str, equipment_id: str, **overrides: object) -> dict:
    body: dict[str, object] = {"equipment_id": equipment_id}
    body.update(overrides)
    resp = client.post(f"/api/v1/campaigns/{cid}/items", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_equipment_catalog_crud(client: TestClient) -> None:
    cid = _demo(client)
    eq = _make_equipment(client, cid, name="Flametongue", item_type="magical", rarity="rare",
                         requires_attunement=True, weight_lb=3.0)
    assert eq["item_type"] == "magical"
    assert eq["rarity"] == "rare"
    assert eq["requires_attunement"] is True
    assert eq["weight_lb"] == 3.0  # round-trips as a float, not a string
    assert eq["instance_count"] == 0

    equip_id = eq["entity_id"]
    patched = client.patch(
        f"/api/v1/campaigns/{cid}/equipment/{equip_id}", json={"rarity": "very_rare"}
    ).json()
    assert patched["rarity"] == "very_rare"

    listing = client.get(f"/api/v1/campaigns/{cid}/equipment").json()
    assert any(e["entity_id"] == equip_id for e in listing)


def test_item_instance_lifecycle_and_history(client: TestClient) -> None:
    cid = _demo(client)
    eq = _make_equipment(client, cid, name="Healing Potion", item_type="magical", rarity="common")
    equip_id = eq["entity_id"]
    npc = _entity(client, cid, "npc", "Ismark")

    item = _make_item(client, cid, equip_id, instance_label="cracked vial",
                      initial_holder_type="party")
    item_id = item["item_id"]
    assert item["equipment_name"] == "Healing Potion"
    assert item["current_holder_type"] == "party"
    assert eq_instance_count(client, cid, equip_id) == 1

    # Transfer party -> npc
    moved = client.post(
        f"/api/v1/campaigns/{cid}/items/{item_id}/transfer",
        json={"holder_type": "npc", "holder_id": npc, "reason": "gifted"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["current_holder_name"] == "Ismark"

    history = client.get(f"/api/v1/campaigns/{cid}/items/{item_id}/history").json()
    assert len(history) == 2  # initial placement + the transfer
    assert history[0]["holder_type"] == "party"
    assert history[0]["to_game"] is not None  # closed interval
    assert history[-1]["holder_name"] == "Ismark"
    assert history[-1]["to_game"] is None  # still-open interval


def test_delete_equipment_hides_orphaned_copies(client: TestClient) -> None:
    cid = _demo(client)
    eq = _make_equipment(client, cid, name="Torch")
    equip_id = eq["entity_id"]
    item = _make_item(client, cid, equip_id)
    item_id = item["item_id"]

    # Soft-delete the definition; its copies must vanish from the item views.
    assert client.delete(f"/api/v1/campaigns/{cid}/equipment/{equip_id}").status_code == 204
    assert client.get(f"/api/v1/campaigns/{cid}/items").json() == []
    assert client.get(f"/api/v1/campaigns/{cid}/items/{item_id}").status_code == 404


def test_create_item_rejects_contradictory_holder(client: TestClient) -> None:
    cid = _demo(client)
    eq = _make_equipment(client, cid, name="Rope")
    npc = _entity(client, cid, "npc", "Bystander")
    resp = client.post(
        f"/api/v1/campaigns/{cid}/items",
        json={"equipment_id": eq["entity_id"], "initial_holder_type": "party",
              "initial_holder_id": npc},
    )
    assert resp.status_code == 422, resp.text
    assert "holder_id not allowed" in resp.json()["detail"]


def test_delete_item_is_audited(client: TestClient) -> None:
    cid = _demo(client)
    eq = _make_equipment(client, cid, name="Dagger")
    item = _make_item(client, cid, eq["entity_id"], instance_label="rusty")
    item_id = item["item_id"]

    assert client.delete(f"/api/v1/campaigns/{cid}/items/{item_id}").status_code == 204
    assert client.get(f"/api/v1/campaigns/{cid}/items/{item_id}").status_code == 404

    # The removal is auditable in the event log even though the row is gone.
    events = client.get(f"/api/v1/campaigns/{cid}/events").json()
    assert any(e["event_type"] == "item_removed" for e in events)


def eq_instance_count(client: TestClient, cid: str, equip_id: str) -> int:
    return client.get(f"/api/v1/campaigns/{cid}/equipment/{equip_id}").json()["instance_count"]
