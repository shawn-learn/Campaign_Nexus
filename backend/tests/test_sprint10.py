"""Sprint 10: D&D 5e plugin — schemas, derive, SRD content, facets, conditions."""

from __future__ import annotations

from unittest.mock import patch

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


def test_every_srd_monster_ships_a_rollable_attack(client: TestClient) -> None:
    """The bestiary is only as useful as what you can click on it.

    Every attack's damage must be notation app.core.dice can actually roll — a typo here
    would only surface when a GM clicked it mid-combat.
    """
    from app.core import dice
    from app.modules.rules import registry

    cid = _demo(client)
    system = registry.get_system("dnd5e")
    monsters = client.get(f"/api/v1/campaigns/{cid}/monsters").json()
    assert len(monsters) == 12

    for monster in monsters:
        attacks = system.attack_actions("monster", monster["doc"])
        assert attacks, f"{monster['name']} has no actions"
        for attack in attacks:
            assert attack["name"]
            for part in attack["damage"]:
                if part["dice"] == "0":
                    continue  # a save-only action (Ghost's Horrifying Visage) deals none
                dice.roll(part["dice"])  # raises BadExpression if the pack has a typo


def test_srd_goblin_attacks_match_the_printed_stat_block(client: TestClient) -> None:
    cid = _demo(client)
    goblin = next(
        m for m in client.get(f"/api/v1/campaigns/{cid}/monsters").json() if m["name"] == "Goblin"
    )
    by_name = {a["name"]: a for a in goblin["doc"]["actions"]}
    assert by_name["Scimitar"]["to_hit"] == 4
    assert by_name["Scimitar"]["damage"] == [{"dice": "1d6+2", "type": "slashing"}]
    assert by_name["Shortbow"]["kind"] == "ranged"


def test_a_new_pack_version_refreshes_rather_than_duplicates(client: TestClient, db) -> None:
    """A pack that gains content must reach campaigns that already imported it.

    The old matcher keyed `existing` off the *versioned* source string, so a bumped version
    matched nothing and re-imported the whole pack next to the old copies — two Goblins,
    forever. Never bumping was the only way to avoid that, which meant a pack could never
    correct or extend anything it had shipped.
    """
    from app.modules.rules import bestiary, registry

    cid = _demo(client)
    system = registry.get_system("dnd5e")
    before = client.get(f"/api/v1/campaigns/{cid}/monsters").json()
    goblin_before = next(m for m in before if m["name"] == "Goblin")

    # Ship a "new version" of the pack in which the Goblin has learned something.
    pack = dict(system.content_packs()[0])
    pack["version"] = "9.9.9"
    pack["monsters"] = [
        {**e, "doc": {**e["doc"], "speed": "30 ft. (revised)"}}
        for e in pack["monsters"] if e["name"] == "Goblin"
    ]
    with patch.object(system, "content_packs", return_value=[pack]):
        changed = bestiary.import_content_packs(db, cid, "dnd5e")

    assert changed == 1
    after = client.get(f"/api/v1/campaigns/{cid}/monsters").json()
    goblins = [m for m in after if m["name"] == "Goblin"]
    assert len(goblins) == 1, "the pack refreshed its Goblin; it must not clone one"
    assert goblins[0]["id"] == goblin_before["id"]  # same monster, rewritten in place
    assert goblins[0]["doc"]["speed"] == "30 ft. (revised)"
    assert goblins[0]["source"] == "content_pack:srd51@9.9.9"
    assert len(after) == len(before)  # nothing else appeared


def test_a_pack_refresh_leaves_the_gms_own_monsters_alone(client: TestClient, db) -> None:
    # A variant is copy-on-write (FR-11.4) — it is exactly how you customize a pack monster,
    # so a pack refresh rewriting it would defeat the entire mechanism. Same for an import.
    from app.modules.rules import bestiary, registry

    cid = _demo(client)
    system = registry.get_system("dnd5e")
    goblin = next(
        m for m in client.get(f"/api/v1/campaigns/{cid}/monsters").json() if m["name"] == "Goblin"
    )
    variant = client.post(f"/api/v1/campaigns/{cid}/monsters/{goblin['id']}/variant").json()

    pack = dict(system.content_packs()[0])
    pack["version"] = "9.9.9"
    pack["monsters"] = [
        {**e, "doc": {**e["doc"], "speed": "30 ft. (revised)"}}
        for e in pack["monsters"] if e["name"] == "Goblin"
    ]
    with patch.object(system, "content_packs", return_value=[pack]):
        bestiary.import_content_packs(db, cid, "dnd5e")

    after = client.get(f"/api/v1/campaigns/{cid}/monsters/{variant['id']}").json()
    assert after["source"] == "custom"
    assert after["doc"].get("speed") != "30 ft. (revised)"  # untouched by the refresh
