"""Sprint 9: rules plugin interface, simpletest, stat-block validate/derive round-trip."""

from __future__ import annotations

import pytest
from app.core import dice
from app.modules.rules import registry
from fastapi.testclient import TestClient


def _demo(client: TestClient) -> str:
    return client.get("/api/v1/campaigns").json()[0]["id"]


# --- plugin conformance kit (parameterized over every installed system) -----
@pytest.mark.parametrize("system", registry.all_systems(), ids=lambda s: s.id)
def test_plugin_conformance(system) -> None:
    assert system.id and system.name and system.version
    for sheet_type in system.sheet_types():
        schema = system.sheet_schema(sheet_type)
        assert schema.get("type") == "object"
        layout = system.render_layout(sheet_type)
        assert isinstance(layout.get("sections"), list) and layout["sections"]
        for section in layout["sections"]:
            for field in section["fields"]:
                # The generic renderer cannot guess a system's attribute names (5e has six,
                # Nimble four), so an ability-array must name its own sub-keys.
                if field["role"] == "ability-array":
                    assert field.get("keys"), f"{system.id}/{sheet_type}: {field['key']}"
        # A valid empty-ish doc round-trips through validate/derive without exploding.
        assert isinstance(system.validate(sheet_type, {}), list)

        # Live-play facade: the playbook relies on these for *every* system (docs/04 §6.8).
        status = system.initial_status(sheet_type, {})
        assert isinstance(status, dict)
        profile = system.combat_profile(sheet_type, {}, status)
        ints = ("max_hp", "hp", "initiative", "initiative_mod")
        assert {*ints, "ac", "initiative_dice"} <= profile.keys()
        assert all(isinstance(profile[k], int) for k in ints)
        # `ac` is the number an attack must meet, or None where the system has no such
        # concept — Nimble's armour reduces damage rather than being a target to beat.
        assert profile["ac"] is None or isinstance(profile["ac"], int)
        # `initiative_dice` is None when a system doesn't roll for order (Nimble: the party
        # acts first). When it *is* set, it must be notation the core engine can roll —
        # otherwise the tracker would only discover the typo at the table.
        if profile["initiative_dice"] is not None:
            dice.roll(profile["initiative_dice"])

    # Rests: whatever they are called, they must be durable and self-consistent.
    rests = system.rest_types()
    assert isinstance(rests, list)
    for rest_type in rests:
        assert system.rest_duration_seconds(rest_type) > 0
        assert isinstance(system.apply_rest(rest_type, {}, {}), dict)
    overnight = system.overnight_rest_type()
    assert overnight is None or overnight in rests

    assert system.round_length_seconds() > 0
    assert isinstance(system.travel_pace_table().get("supported"), bool)


def test_combat_profile_carries_ac_and_the_initiative_die_for_5e() -> None:
    # AC and the initiative die are the only route from a stat block to the combat tracker
    # (docs/04 §6.8) — the playbook must never read `armor_class` out of the doc itself.
    system = registry.get_system("dnd5e")
    doc = {"size": "Small", "type": "humanoid", "armor_class": 15, "hit_points": 7,
           "challenge_rating": 0.25, "abilities": {"str": 8, "dex": 14, "int": 10,
                                                   "wis": 8, "cha": 8, "con": 10}}
    profile = system.combat_profile("monster", doc)
    assert profile["ac"] == 15
    assert profile["max_hp"] == 7
    assert profile["initiative_dice"] == "1d20"
    assert profile["initiative_mod"] == 2  # dex 14
    assert profile["initiative"] == 2      # pre-roll seed, replaced once rolled


@pytest.mark.parametrize("system", registry.all_systems(), ids=lambda s: s.id)
def test_with_hit_points_touches_only_hp(system) -> None:
    """The write half of combat_profile's read — it must not disturb the rest of a status.

    end_combat writes a PC's folded HP back through this. Reaching for initial_status
    instead would have been the obvious shortcut and would have silently reset exhaustion
    and conditions every time a fight ended.
    """
    for sheet_type in system.sheet_types():
        status = system.initial_status(sheet_type, {})
        # Whatever this system tracks besides HP, spoil it and check it survives.
        marked = {**status, "conditions": ["poisoned"], "exhaustion": 3, "_probe": "keep me"}
        result = system.with_hit_points(marked, {}, 7)
        assert result["conditions"] == ["poisoned"]
        assert result["exhaustion"] == 3
        assert result["_probe"] == "keep me"
        # And the system's own HP key — whatever it calls it — now reads back as 7.
        profile = system.combat_profile(sheet_type, {}, result)
        if profile["max_hp"] or "hp" in status or "current_hit_points" in status:
            assert profile["hp"] == 7

    # Mutating the caller's dict would corrupt state that is mid-transaction.
    original = system.initial_status(system.sheet_types()[0], {})
    snapshot = dict(original)
    system.with_hit_points(original, {}, 3)
    assert original == snapshot


def test_attack_actions_uses_a_monsters_printed_numbers() -> None:
    # Monsters don't level, so the SRD's printed numbers are the numbers. Nothing to derive.
    system = registry.get_system("dnd5e")
    doc = {
        "size": "Large", "type": "giant", "armor_class": 11, "hit_points": 59,
        "challenge_rating": 2, "abilities": {"str": 19, "dex": 8, "con": 16, "int": 5,
                                             "wis": 7, "cha": 7},
        "actions": [{"name": "Greatclub", "kind": "melee", "to_hit": 6,
                     "damage": [{"dice": "2d8+4", "type": "bludgeoning"}]}],
    }
    attack = system.attack_actions("monster", doc)[0]
    assert attack["to_hit"] == 6
    assert attack["damage"] == [{"dice": "2d8+4", "type": "bludgeoning"}]
    assert attack["crit_rule"] == "double_dice"


def test_attack_actions_derives_a_pcs_numbers_from_the_sheet() -> None:
    """A PC's attack can store ingredients instead of a total, so levelling keeps it honest.

    Hand-editing every attack's bonus on level-up is the kind of edit that's easy to forget
    and hard to notice — the sheet already knows the level and the ability score.
    """
    system = registry.get_system("dnd5e")
    doc = {
        "level": 5, "max_hit_points": 44, "armor_class": 16,
        "abilities": {"str": 18, "dex": 12, "con": 14, "int": 10, "wis": 12, "cha": 8},
        "actions": [{"name": "Longsword", "kind": "melee", "ability": "str",
                     "proficient": True,
                     "damage": [{"dice": "1d8", "type": "slashing", "add_ability": True}]}],
    }
    attack = system.attack_actions("pc", doc)[0]
    # str 18 = +4, level 5 = proficiency +3.
    assert attack["to_hit"] == 7
    assert attack["damage"] == [{"dice": "1d8+4", "type": "slashing"}]

    # Level 9 moves proficiency to +4, and the attack follows without being touched.
    attack = system.attack_actions("pc", {**doc, "level": 9})[0]
    assert attack["to_hit"] == 8
    assert attack["damage"] == [{"dice": "1d8+4", "type": "slashing"}]  # damage has no prof


def test_a_magic_weapons_bonus_reaches_both_the_attack_and_its_damage() -> None:
    system = registry.get_system("dnd5e")
    doc = {
        "level": 5, "max_hit_points": 44, "armor_class": 16,
        "abilities": {"str": 18, "dex": 12, "con": 14, "int": 10, "wis": 12, "cha": 8},
        "actions": [{"name": "Longsword +1", "ability": "str", "proficient": True,
                     "bonus": 1,
                     "damage": [{"dice": "1d8", "type": "slashing", "add_ability": True}]}],
    }
    attack = system.attack_actions("pc", doc)[0]
    assert attack["to_hit"] == 8              # +4 str, +3 proficiency, +1 magic
    assert attack["damage"][0]["dice"] == "1d8+5"  # +4 str, +1 magic


def test_a_literal_to_hit_wins_over_derivation() -> None:
    # Both forms given: the number someone wrote down is the number they meant.
    system = registry.get_system("dnd5e")
    doc = {
        "level": 5, "max_hit_points": 44, "armor_class": 16,
        "abilities": {"str": 18, "dex": 12, "con": 14, "int": 10, "wis": 12, "cha": 8},
        "actions": [{"name": "Odd Blade", "to_hit": 2, "ability": "str", "proficient": True,
                     "damage": [{"dice": "1d8", "type": "slashing"}]}],
    }
    assert system.attack_actions("pc", doc)[0]["to_hit"] == 2


def test_damage_without_add_ability_is_left_exactly_as_authored() -> None:
    system = registry.get_system("dnd5e")
    doc = {
        "level": 5, "max_hit_points": 44, "armor_class": 16,
        "abilities": {"str": 18, "dex": 12, "con": 14, "int": 10, "wis": 12, "cha": 8},
        # Sneak attack dice and elemental riders don't take the ability modifier.
        "actions": [{"name": "Dagger", "ability": "dex", "proficient": True, "damage": [
            {"dice": "1d4", "type": "piercing", "add_ability": True},
            {"dice": "3d6", "type": "fire"},
        ]}],
    }
    attack = system.attack_actions("pc", doc)[0]
    assert attack["damage"] == [
        {"dice": "1d4+1", "type": "piercing"},  # dex 12 = +1
        {"dice": "3d6", "type": "fire"},        # untouched
    ]


def test_a_system_with_no_attack_model_offers_none() -> None:
    assert registry.get_system("nimble").attack_actions("monster", {"level": 1}) == []


def test_combat_profile_has_no_ac_or_initiative_die_for_nimble() -> None:
    # Nimble's armour reduces damage instead of being a target number, and it rolls no
    # initiative at all. Both must surface as None rather than a 5e-shaped guess.
    system = registry.get_system("nimble")
    doc = {"level": 1, "role": "standard", "max_hp": 8, "armor": "light"}
    profile = system.combat_profile("monster", doc)
    assert profile["ac"] is None
    assert profile["initiative_dice"] is None
    assert profile["initiative"] == 0  # monsters act after the party — the ranking is the rule


def test_rule_systems_listed(client: TestClient) -> None:
    systems = client.get("/api/v1/rule-systems").json()
    ids = {s["id"] for s in systems}
    assert "simpletest" in ids
    st = next(s for s in systems if s["id"] == "simpletest")
    assert set(st["sheet_types"]) == {"pc", "npc", "monster"}


def test_schema_and_layout_endpoints(client: TestClient) -> None:
    schema = client.get("/api/v1/rule-systems/simpletest/schema/pc").json()
    assert "level" in schema["properties"]
    layout = client.get("/api/v1/rule-systems/simpletest/layout/pc").json()
    assert layout["sections"][0]["title"] == "Vitals"


def test_validate_endpoint_reports_errors(client: TestClient) -> None:
    ok = client.post(
        "/api/v1/rule-systems/simpletest/validate",
        json={"sheet_type": "pc", "doc": {"level": 3, "hit_points": 24, "armor_class": 15}},
    ).json()
    assert ok["valid"] is True
    assert ok["derived"]["proficiency_bonus"] == 2  # (3-1)//4 + 2
    assert ok["derived"]["power_level"] == 3 + 24 // 10

    bad = client.post(
        "/api/v1/rule-systems/simpletest/validate",
        json={"sheet_type": "pc", "doc": {"level": 99}},  # over max, missing required
    ).json()
    assert bad["valid"] is False and bad["errors"]


def test_stat_block_create_validate_derive_roundtrip(client: TestClient) -> None:
    cid = _demo(client)
    created = client.post(
        f"/api/v1/campaigns/{cid}/stat-blocks",
        json={"rule_system_id": "simpletest", "sheet_type": "pc", "label": "Serah",
              "doc": {"level": 5, "hit_points": 40, "armor_class": 16}},
    )
    assert created.status_code == 201, created.text
    block = created.json()
    assert block["derived"]["power_level"] == 5 + 4  # 40//10
    assert block["schema_version"] == "1.0.0"

    # Edit updates derived values.
    updated = client.put(
        f"/api/v1/campaigns/{cid}/stat-blocks/{block['id']}",
        json={"doc": {"level": 10, "hit_points": 80, "armor_class": 18}},
    ).json()
    assert updated["derived"]["proficiency_bonus"] == 4  # (10-1)//4 + 2
    assert updated["derived"]["power_level"] == 10 + 8


def test_invalid_stat_block_rejected_with_errors(client: TestClient) -> None:
    cid = _demo(client)
    resp = client.post(
        f"/api/v1/campaigns/{cid}/stat-blocks",
        json={"rule_system_id": "simpletest", "sheet_type": "pc",
              "doc": {"hit_points": 10}},  # missing required level/armor_class
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["errors"]


def test_unknown_system_rejected(client: TestClient) -> None:
    cid = _demo(client)
    resp = client.post(
        f"/api/v1/campaigns/{cid}/stat-blocks",
        json={"rule_system_id": "pathfinder", "sheet_type": "pc", "doc": {}},
    )
    assert resp.status_code == 404
