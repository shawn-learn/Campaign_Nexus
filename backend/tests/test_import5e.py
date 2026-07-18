"""Converter tests for the 5etools import layer.

Fixtures are tiny inline snippets (no copyrighted data files are committed). The monster
case asserts the converted doc actually passes the live ``dnd5e`` plugin schema.
"""

from __future__ import annotations

from app.modules.import5e import codes, copyres, items, monsters, spells, tags
from app.modules.rules import registry

# --------------------------------------------------------------------------- #
# Inline fixtures (shape-representative, not full book text)
# --------------------------------------------------------------------------- #
GOBLIN = {
    "name": "Goblin", "source": "MM", "srd": True,
    "size": ["S"], "type": {"type": "humanoid", "tags": ["goblinoid"]},
    "ac": [{"ac": 15, "from": ["{@item leather armor|phb}"]}],
    "hp": {"average": 7, "formula": "2d6"},
    "speed": {"walk": 30},
    "str": 8, "dex": 14, "con": 10, "int": 10, "wis": 8, "cha": 8,
    "cr": "1/4",
    "trait": [{"name": "Nimble Escape",
               "entries": ["The goblin can take the {@action Disengage} action as a bonus action."]}],
    "action": [
        {"name": "Scimitar",
         "entries": ["{@atk mw} {@hit 4} to hit, reach 5 ft. {@h}5 ({@damage 1d6 + 2}) slashing damage."]},
        {"name": "Shortbow",
         "entries": ["{@atk rw} {@hit 4} to hit, range 80/320 ft. {@h}5 ({@damage 1d6 + 2}) piercing damage."]},
    ],
}

LONGSWORD = {
    "name": "Longsword", "source": "PHB", "srd": True,
    "type": "M", "rarity": "none", "weight": 3, "value": 1500,
    "weaponCategory": "martial", "property": ["V"],
    "dmg1": "1d8", "dmgType": "S", "dmg2": "1d10",
}

BAG_OF_HOLDING = {
    "name": "Bag of Holding", "source": "DMG", "srd": True,
    "rarity": "uncommon", "wondrous": True, "weight": 15,
    "entries": ["This bag has an interior space considerably larger than its outside."],
}

FIREBALL = {
    "name": "Fireball", "source": "PHB", "srd": True, "level": 3, "school": "V",
    "time": [{"number": 1, "unit": "action"}],
    "range": {"type": "point", "distance": {"type": "feet", "amount": 150}},
    "components": {"v": True, "s": True, "m": "a tiny ball of bat guano and sulfur"},
    "duration": [{"type": "instant"}],
    "entries": ["Each creature in a 20-foot-radius sphere takes {@damage 8d6} fire damage."],
    "entriesHigherLevel": [{"type": "entries", "name": "At Higher Levels",
                            "entries": ["{@scaledamage 8d6|3-9|1d6} for each slot above 3rd."]}],
    "damageInflict": ["fire"], "savingThrow": ["dexterity"],
}

ITEM_DICTS = {"type": {"M": "Melee Weapon"}, "property": {"V": "Versatile"}}


# --------------------------------------------------------------------------- #
# tags
# --------------------------------------------------------------------------- #
def test_strip_tags_renders_plain_text():
    text = "{@atk mw} {@hit 4} to hit. {@h}5 ({@damage 1d6 + 2}) slashing, save {@dc 13}."
    out = tags.strip_tags(text)
    assert "{@" not in out
    assert "Melee Weapon Attack" in out
    assert "+4" in out and "Hit:" in out and "DC 13" in out


def test_tag_extractors():
    line = "{@atk rw} {@hit 6} to hit. {@h}9 ({@damage 2d6 + 3}) piercing."
    assert tags.attack_kind(line) == "ranged"
    assert tags.to_hit(line) == 6
    assert tags.first_damage(line) == "2d6+3"


# --------------------------------------------------------------------------- #
# monsters
# --------------------------------------------------------------------------- #
def test_parse_cr():
    assert monsters.parse_cr("1/4") == 0.25
    assert monsters.parse_cr("10") == 10.0
    assert monsters.parse_cr({"cr": "5"}) == 5.0
    assert monsters.parse_cr("—") is None


def test_goblin_doc_is_valid_against_plugin():
    doc = monsters.to_monster_doc(GOBLIN)
    assert doc is not None
    assert doc["size"] == "Small"
    assert doc["type"] == "humanoid"
    assert doc["armor_class"] == 15
    assert doc["hit_points"] == 7
    assert doc["challenge_rating"] == 0.25
    assert doc["speed"] == "30 ft."
    assert doc["actions"][0]["to_hit"] == 4
    assert doc["actions"][0]["kind"] == "melee"
    assert doc["actions"][0]["damage"][0]["dice"] == "1d6+2"
    # The real test: it passes the live rule-system schema.
    errors = registry.get_system("dnd5e").validate("monster", doc)
    assert errors == [], errors


def test_xp_derived_from_cr():
    """5etools has no ``xp`` field; without this every encounter scores as trivial."""
    assert monsters.to_monster_doc(GOBLIN)["xp"] == 50           # CR 1/4
    assert monsters.to_monster_doc({**GOBLIN, "cr": "17"})["xp"] == 18000
    assert monsters.to_monster_doc({**GOBLIN, "cr": "0"})["xp"] == 10
    # An explicit override on the cr object wins over the table.
    assert monsters.to_monster_doc({**GOBLIN, "cr": {"cr": "1", "xp": 300}})["xp"] == 300


def test_monster_missing_required_is_skipped():
    broken = {k: v for k, v in GOBLIN.items() if k != "str"}  # no abilities
    assert monsters.to_monster_doc(broken) is None


# --------------------------------------------------------------------------- #
# full stat-block fields
# --------------------------------------------------------------------------- #
#: Shape-representative, own wording — the file commits no book text. Exercises every
#: awkward form the real bestiary uses.
RICH = {
    **GOBLIN,
    "name": "Test Fiend", "source": "MM", "page": 42,
    "cr": "5",
    "alignment": ["C", "E"],
    "ac": [{"ac": 12, "condition": "in bear form"}, {"ac": 16, "from": ["natural armor"]}],
    "hp": {"average": 90, "formula": "12d10 + 24"},
    "save": {"con": "+6", "wis": "+4"},
    "skill": {"perception": "+7", "sleight of hand": "+5", "other": "+2"},
    "senses": ["darkvision 60 ft.", "blindsight 30 ft. (blind beyond this radius)"],
    "languages": ["Common", "telepathy 120 ft."],
    "resist": ["cold", {"resist": ["bludgeoning", "piercing"],
                        "note": "from nonmagical attacks", "cond": True}],
    "immune": [{"special": "damage dealt by its own spells"}],
    "vulnerable": ["radiant"],
    "conditionImmune": ["charmed", "disease"],
    "action": [
        {"name": "Multiattack", "entries": ["The fiend makes two claw attacks."]},
        {"name": "Claw", "entries": [
            "{@atk mw} {@hit 7} to hit, reach 5 ft. {@h}11 ({@damage 2d6 + 4}) slashing "
            "damage plus 7 ({@damage 2d6}) fire damage."]},
    ],
    "bonus": [{"name": "Shift", "entries": ["Moves without provoking."]}],
    "reaction": [{"name": "Riposte", "entries": ["Strikes back when missed."]}],
    "legendary": [{"name": "Sweep (Costs 2 Actions)", "entries": ["Knocks a target prone."]}],
    "legendaryActions": 2,
    "legendaryHeader": ["The fiend can take 2 legendary actions."],
    "spellcasting": [{
        "name": "Innate Spellcasting",
        "headerEntries": ["Its ability is Charisma (spell save {@dc 15}, {@hit 7} to hit). "
                          "It is a 9th-level spellcaster."],
        "will": ["{@spell detect magic}"],
        "daily": {"3e": ["{@spell fireball}"]},
        "spells": {"0": {"spells": ["{@spell mage hand}"]},
                   "1": {"slots": 4, "spells": ["{@spell shield}"]}},
        "ability": "cha",
    }],
    "legendaryGroup": {"name": "Test Fiend", "source": "MM"},
}

LEGENDARY_GROUPS = {
    ("test fiend", "mm"): {
        "name": "Test Fiend", "source": "MM",
        "lairActions": [
            "On initiative count 20, the fiend takes a lair action:",
            {"type": "list", "items": [
                {"name": "Grasping Ash", "entry": "Ash restrains one creature."},
                "The floor becomes difficult terrain.",
            ]},
        ],
        "regionalEffects": [
            "The land within a mile is warped:",
            {"type": "list", "items": ["Water sours.", "Animals flee."]},
            "These effects fade when the fiend dies.",
        ],
    }
}


def _rich():
    return monsters.to_monster_doc(RICH, LEGENDARY_GROUPS)


def test_rich_doc_validates_against_the_plugin_schema():
    """The load-bearing assertion: `additionalProperties: False` catches converter drift."""
    assert registry.get_system("dnd5e").validate("monster", _rich()) == []


def test_ac_prefers_the_unconditional_entry():
    """Taking ac[0] blindly picks a shapechanger's situational AC."""
    doc = _rich()
    assert doc["armor_class"] == 16
    assert doc["armor_class_note"] == "natural armor"


def test_hit_dice_and_alignment():
    doc = _rich()
    assert doc["hit_dice"] == "12d10 + 24"
    assert doc["alignment"] == "chaotic evil"
    assert doc["source"] == "MM" and doc["page"] == 42


def test_saves_and_skills_are_numeric_and_filtered():
    doc = _rich()
    assert doc["saving_throws"] == {"con": 6, "wis": 4}
    # "sleight of hand" is normalised; the pseudo-skill "other" is dropped.
    assert doc["skills"] == {"perception": 7, "sleight_of_hand": 5}


def test_senses_and_telepathy_are_parsed():
    doc = _rich()
    assert doc["senses"]["darkvision"] == 60
    assert doc["senses"]["blindsight"] == 30
    assert doc["senses"]["blind_beyond"] is True
    # Telepathy is filed under languages by 5etools but is not a language.
    assert doc["languages"] == ["Common"]
    assert doc["telepathy"] == 120


def test_damage_groups_keep_their_qualifier():
    doc = _rich()
    assert {"types": ["cold"]} in doc["damage_resistances"]
    assert {"types": ["bludgeoning", "piercing"],
            "note": "from nonmagical attacks"} in doc["damage_resistances"]
    assert doc["damage_immunities"] == [{"special": "damage dealt by its own spells"}]
    assert doc["damage_vulnerabilities"] == [{"types": ["radiant"]}]
    assert doc["condition_immunities"] == ["charmed", "disease"]


def test_damage_parts_carry_type_and_riders():
    claw = next(a for a in _rich()["actions"] if a["name"] == "Claw")
    assert claw["damage"] == [
        {"dice": "2d6+4", "type": "slashing"},
        {"dice": "2d6", "type": "fire"},
    ]


def test_multiattack_is_hoisted_out_of_actions():
    doc = _rich()
    assert [a["name"] for a in doc["actions"]] == ["Claw"]
    assert doc["multiattack"]["attacks"] == [{"name": "Claw", "count": 2}]


def test_multiattack_parse_declines_ambiguous_prose():
    """A wrong guess in the UI is worse than only showing the description."""
    entry = {**RICH, "action": [
        {"name": "Multiattack",
         "entries": ["It makes two attacks, only one of which can be a bite attack."]}]}
    doc = monsters.to_monster_doc(entry, LEGENDARY_GROUPS)
    assert "attacks" not in doc["multiattack"]
    assert doc["multiattack"]["description"].startswith("It makes two attacks")


def test_bonus_actions_and_reactions():
    doc = _rich()
    assert doc["bonus_actions"][0]["name"] == "Shift"
    assert doc["reactions"][0]["name"] == "Riposte"


def test_legendary_count_and_cost_are_read_not_assumed():
    legendary = _rich()["legendary_actions"]
    assert legendary["count"] == 2                      # not the hardcoded 3
    assert legendary["options"][0]["name"] == "Sweep"   # suffix stripped into `cost`
    assert legendary["options"][0]["cost"] == 2
    assert legendary["description"].startswith("The fiend can take")


def test_spellcasting_innate_and_slots():
    block = _rich()["spellcasting"][0]
    assert block["kind"] == "innate" and block["ability"] == "cha"
    assert block["save_dc"] == 15 and block["attack_bonus"] == 7
    assert block["caster_level"] == 9
    assert block["at_will"] == ["detect magic"]
    assert block["per_day"] == [{"uses": 3, "each": True, "spells": ["fireball"]}]
    assert block["slots"] == [
        {"level": 0, "spells": ["mage hand"]},
        {"level": 1, "slots": 4, "spells": ["shield"]},
    ]


def test_lair_and_regional_come_from_the_legendary_group():
    """Neither is stored on the monster; without the join no creature has a lair action."""
    doc = _rich()
    lair = doc["lair_actions"]
    assert lair["initiative"] == 20
    assert [o["name"] for o in lair["options"]] == ["Grasping Ash", ""]
    regional = doc["regional_effects"]
    assert [e["description"] for e in regional["effects"]] == ["Water sours.", "Animals flee."]
    assert regional["fades"] == "These effects fade when the fiend dies."


def test_lair_is_omitted_without_the_group_index():
    assert "lair_actions" not in monsters.to_monster_doc(RICH)


def test_special_hit_points_parse_a_leading_number():
    entry = {**GOBLIN, "hp": {"special": "20"}}
    assert monsters.to_monster_doc(entry)["hit_points"] == 20


def test_optional_fields_stay_absent_rather_than_null():
    """An empty optional must not become `null` in the stored document."""
    doc = monsters.to_monster_doc(GOBLIN)
    for key in ("saving_throws", "skills", "senses", "languages", "spellcasting"):
        assert key not in doc


def test_damage_parts_helper():
    assert tags.damage_parts("{@h}5 ({@damage 1d6 + 2}) slashing damage.") == [
        {"dice": "1d6+2", "type": "slashing"}]
    assert tags.damage_parts("no damage tags here") == []


# --------------------------------------------------------------------------- #
# copyres — 5etools ``_copy`` variants
# --------------------------------------------------------------------------- #
#: A variant that restates only its own attack; everything else comes from GOBLIN.
GOBLIN_SENTRY = {
    "name": "Goblin Sentry", "source": "XYZ",
    "_copy": {"name": "Goblin", "source": "MM"},
    "action": [{"name": "Spear",
                "entries": ["{@atk mw} {@hit 4} to hit, reach 5 ft. {@h}5 ({@damage 1d8 + 2}) piercing damage."]}],
}


def _index():
    return copyres.build_index([GOBLIN, GOBLIN_SENTRY])


def test_resolve_copy_inherits_base_body():
    resolved = copyres.resolve_copy(GOBLIN_SENTRY, _index())
    assert resolved["name"] == "Goblin Sentry"
    assert resolved["ac"] == GOBLIN["ac"]          # inherited
    assert resolved["hp"]["average"] == 7
    assert resolved["str"] == 8
    assert resolved["action"][0]["name"] == "Spear"  # own key wins
    assert "_copy" not in resolved


def test_copy_variant_converts_and_validates():
    """The bug this guards: an unresolved ``_copy`` has no size/ac/hp and converts to None."""
    assert monsters.to_monster_doc(GOBLIN_SENTRY) is None
    doc = monsters.to_monster_doc(copyres.resolve_copy(GOBLIN_SENTRY, _index()))
    assert doc is not None
    assert doc["armor_class"] == 15 and doc["hit_points"] == 7
    assert doc["actions"][0]["name"] == "Spear"
    assert registry.get_system("dnd5e").validate("monster", doc) == []


def test_chained_copy_resolves_through_both_levels():
    elite = {"name": "Goblin Elite", "source": "XYZ",
             "_copy": {"name": "Goblin Sentry", "source": "XYZ"}, "cr": "1"}
    index = copyres.build_index([GOBLIN, GOBLIN_SENTRY, elite])
    resolved = copyres.resolve_copy(elite, index)
    assert resolved["ac"] == GOBLIN["ac"]                 # from the grandparent
    assert resolved["action"][0]["name"] == "Spear"       # from the parent
    assert resolved["cr"] == "1"                          # own


def test_missing_base_degrades_instead_of_raising():
    orphan = {"name": "Orphan", "source": "XYZ", "_copy": {"name": "Nope", "source": "XYZ"}}
    assert copyres.resolve_copy(orphan, _index()) == {"name": "Orphan", "source": "XYZ"}


def test_cyclic_copy_terminates():
    a = {"name": "A", "source": "X", "_copy": {"name": "B", "source": "X"}}
    b = {"name": "B", "source": "X", "_copy": {"name": "A", "source": "X"}}
    assert copyres.resolve_copy(a, copyres.build_index([a, b]))["name"] == "A"


def _mod_copy(mod, **extra):
    entry = {"name": "V", "source": "X", "_copy": {"name": "Goblin", "source": "MM", "_mod": mod}}
    entry.update(extra)
    return copyres.resolve_copy(entry, _index())


def test_mod_replace_txt_rewrites_nested_strings():
    out = _mod_copy({"*": {"mode": "replaceTxt", "replace": "the goblin", "with": "Snik", "flags": "i"}})
    assert "Snik can take" in out["trait"][0]["entries"][0]
    assert out["name"] == "V"  # identity keys are never rewritten


def test_mod_array_ops():
    spear = {"name": "Spear", "entries": ["stab"]}
    assert _mod_copy({"action": {"mode": "appendArr", "items": spear}})["action"][-1] == spear
    assert _mod_copy({"action": {"mode": "prependArr", "items": spear}})["action"][0] == spear
    assert _mod_copy({"action": {"mode": "insertArr", "index": 1, "items": spear}})["action"][1] == spear

    replaced = _mod_copy({"action": {"mode": "replaceArr", "replace": "Scimitar", "items": spear}})
    assert [a["name"] for a in replaced["action"]] == ["Spear", "Shortbow"]

    removed = _mod_copy({"action": {"mode": "removeArr", "names": "Shortbow"}})
    assert [a["name"] for a in removed["action"]] == ["Scimitar"]


def test_mod_append_if_not_exists_is_idempotent():
    out = _mod_copy({"languages": {"mode": "appendIfNotExistsArr", "items": ["Common", "Common"]}})
    assert out["languages"] == ["Common"]


def test_mod_set_prop_null_removes():
    assert "speed" not in _mod_copy({"_": {"mode": "setProp", "prop": "speed", "value": None}})
    assert _mod_copy({"_": {"mode": "setProp", "prop": "page", "value": 7}})["page"] == 7


def test_mod_add_skills_merges():
    assert _mod_copy({"_": {"mode": "addSkills", "skills": {"investigation": 2}}})["skill"] == {
        "investigation": 2
    }


def test_noise_keys_are_stripped():
    resolved = copyres.resolve_copy(
        {"name": "N", "source": "X", "hasToken": True, "damageTags": ["P"], "srd": True}, _index()
    )
    assert "hasToken" not in resolved and "damageTags" not in resolved
    assert resolved["srd"] is True  # licensing flags must survive for sources.is_srd


# --------------------------------------------------------------------------- #
# items
# --------------------------------------------------------------------------- #
def test_money_str():
    assert items.money_str(1500) == "15 gp"
    assert items.money_str(50) == "5 sp"
    assert items.money_str(1) == "1 cp"
    assert items.money_str(0) is None


def test_base_item_longsword():
    entry = items.to_library_entry(LONGSWORD, ITEM_DICTS, source="phb", is_base=True)
    assert entry["item_type"] == "mundane"
    assert entry["rarity"] is None
    assert entry["value_gp"] == "15 gp"
    assert entry["weight_lb"] == 3.0
    assert "1d8 slashing" in entry["properties"]
    assert "versatile (1d10)" in entry["properties"]


def test_magic_item_bag_of_holding():
    entry = items.to_library_entry(BAG_OF_HOLDING, ITEM_DICTS, source="dmg")
    assert entry["item_type"] == "magical"
    assert entry["rarity"] == "uncommon"
    assert entry["weight_lb"] == 15.0
    assert entry["requires_attunement"] is False
    assert "interior space" in entry["properties"]


# --------------------------------------------------------------------------- #
# spells
# --------------------------------------------------------------------------- #
def test_fireball_conversion():
    out = spells.to_spell(FIREBALL, classes=["Sorcerer", "Wizard"])
    assert out["level"] == 3
    assert out["school"] == "Evocation"
    assert out["casting_time"] == "1 action"
    assert out["range_text"] == "150 feet"
    assert out["component_v"] and out["component_s"] and out["component_m"]
    assert out["material"].startswith("a tiny ball")
    assert out["concentration"] is False
    assert out["duration"] == "Instantaneous"
    assert out["classes"] == "Sorcerer, Wizard"
    assert out["damage_types"] == "fire"
    assert out["saving_throw"] == "dexterity"
    assert "{@" not in out["description"]
    assert out["higher_levels"] and "{@" not in out["higher_levels"]


def test_class_map_inversion():
    sources = {"PHB": {"Fireball": {"class": [{"name": "Wizard"}, {"name": "Sorcerer"}]}}}
    cmap = spells.load_class_map(sources)
    assert cmap[("Fireball", "PHB")] == ["Sorcerer", "Wizard"]


def test_codes_build_item_dicts():
    base = {
        "itemType": [{"abbreviation": "M", "name": "Melee Weapon"}],
        "itemProperty": [{"abbreviation": "V", "entries": [{"name": "Versatile"}]}],
    }
    dicts = codes.build_item_dicts(base)
    assert dicts["type"]["M"] == "Melee Weapon"
    assert dicts["property"]["V"] == "Versatile"
