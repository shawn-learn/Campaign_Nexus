"""Bestiary and full-campaign JSON export/import round-trips (FR-1.6, FR-11.4)."""

from __future__ import annotations

from fastapi.testclient import TestClient

_AB = {"str": 10, "dex": 14, "con": 14, "int": 8, "wis": 12, "cha": 10}


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


# --- bestiary --------------------------------------------------------------
def test_bestiary_export_import_roundtrip(client: TestClient) -> None:
    cid = _demo(client)
    export = client.get(f"/api/v1/campaigns/{cid}/monsters/export").json()
    assert export["kind"] == "bestiary"
    assert any(m["name"] == "Wight" for m in export["monsters"])

    # Import into a fresh (simpletest? no — needs dnd5e) campaign.
    other = client.post("/api/v1/campaigns", json={"name": "Fresh"}).json()["id"]
    before = len(client.get(f"/api/v1/campaigns/{other}/monsters").json())
    result = client.post(f"/api/v1/campaigns/{other}/monsters/import-json", json=export).json()
    assert result["imported"] == len(export["monsters"])
    assert result["errors"] == []
    after = client.get(f"/api/v1/campaigns/{other}/monsters").json()
    assert len(after) == before + len(export["monsters"])
    assert any(m["name"] == "Wight" and m["source"] == "imported" for m in after)


def test_bestiary_import_reports_invalid(client: TestClient) -> None:
    cid = _demo(client)
    payload = {"kind": "bestiary", "monsters": [
        {"name": "Bad", "doc": {"size": "Medium"}},  # missing required fields
        {"name": "", "doc": {}},  # missing name
    ]}
    result = client.post(f"/api/v1/campaigns/{cid}/monsters/import-json", json=payload).json()
    assert result["imported"] == 0
    assert len(result["errors"]) == 2


# --- full campaign ---------------------------------------------------------
def test_campaign_export_import_roundtrip(client: TestClient) -> None:
    cid = _demo(client)
    # Build a small campaign: linked entities, article w/ mention, a PC, an encounter,
    # a manual timeline entry, an advanced clock.
    npc = client.post(f"/api/v1/campaigns/{cid}/entities",
                      json={"entity_type": "npc", "name": "Serah Voss"}).json()["id"]
    loc = client.post(f"/api/v1/campaigns/{cid}/entities",
                      json={"entity_type": "location", "name": "Barrow Tavern"}).json()["id"]
    client.post(f"/api/v1/campaigns/{cid}/entities/{npc}/links",
                json={"to_entity": loc, "link_type_id": "located_at"})
    client.post(f"/api/v1/campaigns/{cid}/entities/{npc}/tags", json={"name": "questgiver"})
    client.post(f"/api/v1/campaigns/{cid}/stat-blocks",
                json={"rule_system_id": "dnd5e", "sheet_type": "pc", "label": "Serah",
                      "doc": {"level": 5, "max_hit_points": 44, "armor_class": 16,
                              "abilities": _AB}})
    client.post(f"/api/v1/campaigns/{cid}/timeline/manual",
                json={"title": "The Sundering", "occurred_at_game": -1000, "significance": 4})
    client.post(f"/api/v1/campaigns/{cid}/clock/advance", json={"hours": 8, "reason": "long rest"})

    archive = client.get(f"/api/v1/campaigns/{cid}/export").json()
    assert archive["kind"] == "campaign"

    # Import as a new campaign.
    imported = client.post("/api/v1/campaigns/import", json=archive)
    assert imported.status_code == 201, imported.text
    new_cid = imported.json()["id"]
    assert new_cid != cid

    # Entities came across (SRD bestiary entities are stat blocks, not wiki entities).
    entities = client.get(f"/api/v1/campaigns/{new_cid}/entities").json()
    names = {e["name"] for e in entities}
    assert {"Serah Voss", "Barrow Tavern"} <= names

    # The located_at link + backlink survived (ids remapped).
    new_npc = next(e["id"] for e in entities if e["name"] == "Serah Voss")
    detail = client.get(f"/api/v1/campaigns/{new_cid}/entities/{new_npc}").json()
    assert any(o["entity_type"] == "location" for o in detail["outbound"])

    # Tag, clock, timeline, and bestiary all carried over.
    assert any(t["name"] == "questgiver" for e in entities for t in e["tags"])
    assert client.get(f"/api/v1/campaigns/{new_cid}/clock").json()["time_game"] == 8 * 3600
    tl = client.get(f"/api/v1/campaigns/{new_cid}/timeline",
                    params={"include_hidden": "true"}).json()
    assert any(t["title"] == "The Sundering" for t in tl)
    monsters = client.get(f"/api/v1/campaigns/{new_cid}/monsters").json()
    assert any(m["name"] == "Wight" for m in monsters)

    # Search index rebuilt for imported entities.
    hits = client.get(f"/api/v1/campaigns/{new_cid}/search", params={"q": "serah"}).json()
    assert any(h["name"] == "Serah Voss" for h in hits)


def test_import_rejects_non_campaign_archive(client: TestClient) -> None:
    resp = client.post("/api/v1/campaigns/import", json={"kind": "bestiary", "monsters": []})
    assert resp.status_code == 422


def test_import_rejects_structurally_broken_archive(client: TestClient) -> None:
    # A "campaign" archive missing its required body, and one with undecodable media bytes,
    # must both fail cleanly as 422 rather than crashing the importer with a 500.
    missing_body = client.post("/api/v1/campaigns/import", json={"kind": "campaign"})
    assert missing_body.status_code == 422, missing_body.text

    bad_media = client.post("/api/v1/campaigns/import", json={
        "kind": "campaign",
        "campaign": {"name": "Broken", "rule_system_id": "dnd5e"},
        "media": [{"id": "m1", "filename": "x.png", "data_b64": "not-valid-base64!!"}],
    })
    assert bad_media.status_code == 422, bad_media.text
