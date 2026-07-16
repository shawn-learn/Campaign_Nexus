from __future__ import annotations

from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def _library(client: TestClient, **query: str) -> list[dict]:
    return client.get("/api/v1/equipment-library", params=query).json()


def test_starter_library_is_seeded(client: TestClient) -> None:
    entries = _library(client)
    names = {e["name"] for e in entries}
    assert "Potion of Healing" in names
    assert "Longsword" in names
    # Seeded content is marked srd.
    assert all(e["source"] == "srd" for e in entries if e["name"] == "Longsword")


def test_library_filters(client: TestClient) -> None:
    magical = _library(client, item_type="magical")
    assert magical and all(e["item_type"] == "magical" for e in magical)
    potions = _library(client, q="potion")
    assert potions and all("potion" in e["name"].lower() for e in potions)


def test_create_custom_library_entry(client: TestClient) -> None:
    created = client.post(
        "/api/v1/equipment-library",
        json={"name": "Sunsword", "item_type": "magical", "rarity": "legendary",
              "requires_attunement": True, "weight_lb": 3.0},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source"] == "custom"
    assert body["rarity"] == "legendary"
    assert body["weight_lb"] == 3.0


def test_import_creates_campaign_definition_and_dedupes(client: TestClient) -> None:
    cid = _demo(client)
    entry = next(e for e in _library(client) if e["name"] == "Longsword")

    imported = client.post(
        f"/api/v1/campaigns/{cid}/equipment/import", json={"library_id": entry["id"]}
    )
    assert imported.status_code == 201, imported.text
    eq = imported.json()
    assert eq["name"] == "Longsword"
    assert eq["library_id"] == entry["id"]
    equip_id = eq["entity_id"]

    # Re-importing the same template is idempotent: same definition, no duplicate.
    again = client.post(
        f"/api/v1/campaigns/{cid}/equipment/import", json={"library_id": entry["id"]}
    )
    assert again.status_code == 201
    assert again.json()["entity_id"] == equip_id

    catalog = client.get(f"/api/v1/campaigns/{cid}/equipment").json()
    longswords = [e for e in catalog if e["name"] == "Longsword"]
    assert len(longswords) == 1  # not duplicated


def test_import_unknown_entry_404(client: TestClient) -> None:
    cid = _demo(client)
    resp = client.post(
        f"/api/v1/campaigns/{cid}/equipment/import", json={"library_id": "does-not-exist"}
    )
    assert resp.status_code == 404


def test_save_campaign_definition_to_library(client: TestClient) -> None:
    cid = _demo(client)
    made = client.post(
        f"/api/v1/campaigns/{cid}/equipment",
        json={"name": "Heirloom Blade", "item_type": "magical", "rarity": "rare"},
    ).json()

    saved = client.post(
        f"/api/v1/campaigns/{cid}/equipment/{made['entity_id']}/save-to-library"
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["source"] == "custom"
    assert any(e["name"] == "Heirloom Blade" for e in _library(client))


def test_update_and_delete_library_entry(client: TestClient) -> None:
    entry = client.post(
        "/api/v1/equipment-library", json={"name": "Trinket", "item_type": "mundane"}
    ).json()
    entry_id = entry["id"]

    patched = client.patch(
        f"/api/v1/equipment-library/{entry_id}", json={"value_gp": "1 gp"}
    ).json()
    assert patched["value_gp"] == "1 gp"

    assert client.delete(f"/api/v1/equipment-library/{entry_id}").status_code == 204
    assert client.get(f"/api/v1/equipment-library/{entry_id}").status_code == 404
