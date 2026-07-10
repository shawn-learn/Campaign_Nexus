"""Sprint 10: D&D 5e plugin — schemas, derive, SRD content, facets, conditions."""

from __future__ import annotations

from app.modules.rules import registry
from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


def test_5e_registered_with_sheet_types(client: TestClient) -> None:
    ids = {s["id"] for s in client.get("/api/v1/rule-systems").json()}
    assert "dnd5e" in ids
    assert registry.get_system("dnd5e").sheet_types() == ["pc", "npc", "monster"]


def test_5e_pc_derive() -> None:
    system = registry.get_system("dnd5e")
    doc = {
        "level": 5, "max_hit_points": 44, "armor_class": 16,
        "abilities": {"str": 10, "dex": 16, "con": 14, "int": 8, "wis": 12, "cha": 18},
        "spellcasting_ability": "cha",
    }
    assert system.validate("pc", doc) == []
    d = system.derive("pc", doc)
    assert d["proficiency_bonus"] == 3  # level 5
    assert d["ability_modifiers"]["dex"] == 3
    assert d["initiative"] == 3
    assert d["spell_save_dc"] == 8 + 3 + 4  # prof + cha mod(+4)


def test_5e_validation_rejects_bad_doc(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/rule-systems/dnd5e/validate",
        json={"sheet_type": "pc", "doc": {"level": 25, "armor_class": 16}},  # over max, missing
    ).json()
    assert resp["valid"] is False
    assert resp["errors"]


def test_5e_conditions_and_facets(client: TestClient) -> None:
    conditions = client.get("/api/v1/rule-systems/dnd5e/conditions").json()
    names = {c["id"] for c in conditions}
    assert {"prone", "poisoned", "unconscious"} <= names and len(conditions) == 15

    facets = client.get("/api/v1/rule-systems/dnd5e/facets").json()
    assert {f["label"] for f in facets} == {"CR", "XP", "Type", "Size"}


def test_srd_bestiary_imported_for_demo(client: TestClient) -> None:
    cid = _demo(client)
    monsters = client.get(f"/api/v1/campaigns/{cid}/monsters").json()
    names = {m["name"] for m in monsters}
    assert {"Goblin", "Wight", "Ghost", "Owlbear"} <= names
    wight = next(m for m in monsters if m["name"] == "Wight")
    assert wight["facets"]["facet1_num"] == 3.0  # CR
    assert wight["facets"]["facet1_text"] == "undead"
    assert wight["source"].startswith("content_pack:srd51")
    # derived proficiency from CR is present on the stat block.
    assert wight["derived"]["proficiency_bonus"] == 2


def test_import_is_idempotent(client: TestClient) -> None:
    cid = _demo(client)
    before = len(client.get(f"/api/v1/campaigns/{cid}/monsters").json())
    result = client.post(
        f"/api/v1/campaigns/{cid}/monsters/import", params={"system_id": "dnd5e"}
    ).json()
    assert result["imported"] == 0  # already seeded on startup
    after = len(client.get(f"/api/v1/campaigns/{cid}/monsters").json())
    assert after == before
