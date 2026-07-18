"""The 5e plugin's monster schema and derivations.

The full stat-block fields (saves, skills, senses, spellcasting, lair…) were added after
~3,700 monsters had already been imported, so the first test here is the one that matters
most: those older documents must still validate.
"""

from __future__ import annotations

from app.modules.rules import registry
from app.modules.rules.systems.dnd5e import _MONSTER_LAYOUT, _MONSTER_SCHEMA

SYSTEM = registry.get_system("dnd5e")
_AB = {"str": 10, "dex": 14, "con": 12, "int": 8, "wis": 10, "cha": 16}

#: Exactly the six required fields — the shape every pre-5.2.0 import produced.
LEGACY = {"size": "Medium", "type": "humanoid", "armor_class": 12, "hit_points": 9,
          "challenge_rating": 0.25, "abilities": _AB}

#: One of everything the 5.2.0 schema added.
FULL = {
    **LEGACY,
    "xp": 50, "speed": "30 ft., fly 60 ft.", "alignment": "chaotic evil",
    "armor_class_note": "natural armor", "hit_dice": "2d8", "hit_points_note": "",
    "saving_throws": {"dex": 5, "wis": 3},
    "skills": {"perception": 13, "stealth": 6},
    "senses": {"darkvision": 60, "blindsight": 30, "blind_beyond": True, "other": ["keen smell"]},
    "languages": ["Common", "understands Abyssal but can't speak it"], "telepathy": 120,
    "damage_resistances": [{"types": ["cold", "fire"]},
                           {"types": ["bludgeoning"], "note": "from nonmagical attacks"}],
    "damage_immunities": [{"special": "damage from spells"}],
    "damage_vulnerabilities": [{"types": ["radiant"]}],
    "condition_immunities": ["charmed", "disease"],
    "multiattack": {"description": "Makes two claw attacks.",
                    "attacks": [{"name": "Claw", "count": 2}]},
    "traits": [{"name": "Pack Tactics", "description": "Advantage when allies are near."}],
    "actions": [{"name": "Claw", "kind": "melee", "to_hit": 5,
                 "damage": [{"dice": "1d6+3", "type": "slashing"}]}],
    "bonus_actions": [{"name": "Nimble Escape", "description": "Disengage as a bonus action."}],
    "reactions": [{"name": "Parry", "description": "+2 AC against one melee attack."}],
    "legendary_actions": {"count": 3, "description": "Three per round.",
                          "options": [{"name": "Tail", "cost": 2, "to_hit": 5}]},
    "spellcasting": [{
        "name": "Innate Spellcasting", "kind": "innate", "ability": "cha",
        "save_dc": 15, "attack_bonus": 7, "description": "Requires no material components.",
        "at_will": ["detect magic"],
        "per_day": [{"uses": 3, "each": True, "spells": ["fireball"]}],
        "slots": [{"level": 0, "spells": ["mage hand"]},
                  {"level": 1, "slots": 4, "spells": ["shield"]}],
    }],
    "lair_actions": {"description": "On initiative 20…", "initiative": 20,
                     "options": [{"name": "Grasping Vines", "description": "Restrains a target."}]},
    "regional_effects": {"description": "Within 6 miles…", "fades": "Ends at death.",
                         "effects": [{"name": "Mist", "description": "Fog blankets the valley."}]},
    "source": "MM", "page": 42,
}


# --------------------------------------------------------------------------- #
# schema
# --------------------------------------------------------------------------- #
def test_legacy_monster_doc_still_validates():
    """The guard for every monster imported before these fields existed."""
    assert SYSTEM.validate("monster", LEGACY) == []


def test_full_monster_doc_validates():
    assert SYSTEM.validate("monster", FULL) == []


def test_unknown_field_is_still_rejected():
    """`additionalProperties: False` is what turns converter drift into a test failure."""
    assert SYSTEM.validate("monster", {**LEGACY, "mythic_actions": {}}) != []


def test_unknown_skill_key_is_rejected():
    assert SYSTEM.validate("monster", {**LEGACY, "skills": {"basketweaving": 3}}) != []


def test_condition_immunities_accept_non_srd_values():
    """Real bestiary data ships "disease", which 5e never defined as a condition."""
    assert SYSTEM.validate("monster", {**LEGACY, "condition_immunities": ["disease"]}) == []


# --------------------------------------------------------------------------- #
# derive
# --------------------------------------------------------------------------- #
def test_passive_perception_uses_the_perception_skill():
    """Was 10 + wis for every monster, understating anything with Perception proficiency."""
    assert SYSTEM.derive("monster", LEGACY)["passive_perception"] == 10  # wis 10 -> +0
    assert SYSTEM.derive("monster", FULL)["passive_perception"] == 23    # printed +13


def test_saves_and_skills_complete_from_ability_modifiers():
    derived = SYSTEM.derive("monster", FULL)
    assert derived["saving_throws"]["dex"] == 5   # printed value wins
    assert derived["saving_throws"]["str"] == 0   # unlisted -> bare modifier, not +prof
    assert derived["skill_modifiers"]["stealth"] == 6
    assert derived["skill_modifiers"]["arcana"] == -1  # int 8 -> -1
    assert len(derived["skill_modifiers"]) == 18       # always the complete map


def test_spell_dc_is_derived_when_not_printed():
    doc = {**LEGACY, "challenge_rating": 5,
           "spellcasting": [{"kind": "prepared", "ability": "cha"}]}
    derived = SYSTEM.derive("monster", doc)
    assert derived["spell_save_dc"] == 8 + 3 + 3     # prof 3 (CR 5) + cha +3
    assert derived["spell_attack_bonus"] == 3 + 3


def test_printed_spell_dc_wins_over_derivation():
    assert SYSTEM.derive("monster", FULL)["spell_save_dc"] == 15


# --------------------------------------------------------------------------- #
# lair
# --------------------------------------------------------------------------- #
def test_combat_profile_reports_lair():
    lair = SYSTEM.combat_profile("monster", FULL)
    assert lair["has_lair"] is True and lair["lair_initiative"] == 20
    plain = SYSTEM.combat_profile("monster", LEGACY)
    assert plain["has_lair"] is False and plain["lair_initiative"] is None


def test_lair_initiative_is_the_plugins_to_choose():
    """Default 20 comes from the plugin, so the tracker never encodes a 5e rule."""
    doc = {**LEGACY, "lair_actions": {"options": []}}
    assert SYSTEM.combat_profile("monster", doc)["lair_initiative"] == 20
    doc = {**LEGACY, "lair_actions": {"initiative": 15, "options": []}}
    assert SYSTEM.combat_profile("monster", doc)["lair_initiative"] == 15


# --------------------------------------------------------------------------- #
# attack_actions
# --------------------------------------------------------------------------- #
def test_attack_actions_group_every_heading():
    by_name = {a["name"]: a for a in SYSTEM.attack_actions("monster", FULL)}
    assert by_name["Claw"]["group"] == "action"
    assert by_name["Nimble Escape"]["group"] == "bonus"
    assert by_name["Parry"]["group"] == "reaction"
    assert by_name["Tail"]["group"] == "legendary"
    assert by_name["Grasping Vines"]["group"] == "lair"


def test_legendary_cost_still_marks_only_legendary_options():
    by_name = {a["name"]: a for a in SYSTEM.attack_actions("monster", FULL)}
    assert by_name["Tail"]["legendary_cost"] == 2
    assert by_name["Claw"]["legendary_cost"] is None


def test_prose_only_entries_resolve_without_an_attack_roll():
    lair = next(a for a in SYSTEM.attack_actions("monster", FULL) if a["group"] == "lair")
    assert lair["to_hit"] is None and lair["damage"] == []


# --------------------------------------------------------------------------- #
# layout coverage
# --------------------------------------------------------------------------- #
#: Fields the bespoke StatBlock5e renderer shows but the schema-driven editor cannot yet
#: edit: they need new field roles (modifier maps, string lists, nested groups) in
#: `interface.FIELD_ROLES` and `GenericSheetRenderer`. Import-populated and read-only for
#: now — this list is the explicit record of that, so it can't rot silently.
_RENDER_ONLY = {
    "saving_throws", "skills", "senses", "languages", "telepathy",
    "damage_resistances", "damage_immunities", "damage_vulnerabilities",
    "condition_immunities", "multiattack", "spellcasting", "lair_actions",
    "regional_effects", "armor_class_note", "hit_points_note", "page",
    # An object wrapping a count + option list; `attack-list` edits a bare array, so this
    # needs its own role before the editor can touch it.
    "legendary_actions",
}


def test_every_schema_field_is_editable_or_explicitly_render_only():
    laid_out = {
        field["key"]
        for section in _MONSTER_LAYOUT["sections"]
        for field in section["fields"]
    }
    unaccounted = set(_MONSTER_SCHEMA["properties"]) - laid_out - _RENDER_ONLY
    assert unaccounted == set(), f"add to _MONSTER_LAYOUT or _RENDER_ONLY: {unaccounted}"
