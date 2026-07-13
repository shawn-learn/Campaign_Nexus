"""D&D 5e rule-system plugin (docs/08, §10.7).

Ships SRD 5.1 content under CC-BY-4.0 (see ``content.ATTRIBUTION``). Kept behind the
``RuleSystem`` interface like any other system — core has no 5e-specific knowledge.
"""

from __future__ import annotations

from typing import Any, ClassVar

from app.modules.rules.interface import (
    BaseRuleSystem,
    CombatProfile,
    ConditionDef,
    ContentPack,
    Document,
    FacetDef,
    FacetValues,
    JsonSchema,
    LayoutSpec,
    SkillCheckDcs,
    TravelPaceTable,
)
from app.modules.rules.systems.dnd5e.content import CONTENT_PACK

_ABILITIES = ("str", "dex", "con", "int", "wis", "cha")
_SIZES = ["Tiny", "Small", "Medium", "Large", "Huge", "Gargantuan"]

_ability_scores: JsonSchema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {a: {"type": "integer", "minimum": 1, "maximum": 30} for a in _ABILITIES},
    "required": list(_ABILITIES),
}

_CHARACTER_SCHEMA: JsonSchema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "class_name": {"type": "string"},
        "level": {"type": "integer", "minimum": 1, "maximum": 20},
        "abilities": _ability_scores,
        "max_hit_points": {"type": "integer", "minimum": 1},
        "current_hit_points": {"type": "integer", "minimum": 0},
        "armor_class": {"type": "integer", "minimum": 1},
        "proficient_saves": {"type": "array", "items": {"enum": list(_ABILITIES)}},
        "spellcasting_ability": {"enum": [*_ABILITIES, None]},
        "notes": {"type": "string"},
    },
    "required": ["level", "abilities", "max_hit_points", "armor_class"],
}

_MONSTER_SCHEMA: JsonSchema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "size": {"enum": _SIZES},
        "type": {"type": "string"},
        "armor_class": {"type": "integer", "minimum": 1},
        "hit_points": {"type": "integer", "minimum": 1},
        "challenge_rating": {"type": "number", "minimum": 0},
        "xp": {"type": "integer", "minimum": 0},
        "abilities": _ability_scores,
        "speed": {"type": "string"},
        "traits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "description": {"type": "string"}},
            },
        },
    },
    "required": ["size", "type", "armor_class", "hit_points", "challenge_rating", "abilities"],
}

# Proficiency bonus by challenge rating (SRD table, condensed).
_CR_PROFICIENCY = [(1, 2), (4, 2), (8, 3), (12, 4), (16, 5), (20, 6), (30, 9)]

# Per-character XP thresholds by level: (easy, medium, hard, deadly) (SRD DMG).
_XP_THRESHOLDS: dict[int, tuple[int, int, int, int]] = {
    1: (25, 50, 75, 100), 2: (50, 100, 150, 200), 3: (75, 150, 225, 400),
    4: (125, 250, 375, 500), 5: (250, 500, 750, 1100), 6: (300, 600, 900, 1400),
    7: (350, 750, 1100, 1700), 8: (450, 900, 1300, 1900), 9: (550, 1100, 1600, 2400),
    10: (600, 1200, 1900, 2800), 11: (800, 1600, 2400, 3600), 12: (1000, 2000, 3000, 4500),
    13: (1100, 2200, 3400, 5100), 14: (1250, 2500, 3800, 5700), 15: (1400, 2800, 4300, 6400),
    16: (1600, 3200, 4800, 7200), 17: (2000, 3900, 5900, 8800), 18: (2100, 4200, 6300, 9500),
    19: (2400, 4900, 7300, 10900), 20: (2800, 5700, 8500, 12700),
}


def _encounter_multiplier(num_monsters: int) -> float:
    if num_monsters <= 1:
        return 1.0
    if num_monsters == 2:
        return 1.5
    if num_monsters <= 6:
        return 2.0
    if num_monsters <= 10:
        return 2.5
    if num_monsters <= 14:
        return 3.0
    return 4.0

_CONDITIONS: list[ConditionDef] = [
    {"id": c, "name": c.capitalize(), "description": desc}
    for c, desc in [
        ("blinded", "Can't see; attacks against have advantage, its attacks have disadvantage."),
        ("charmed", "Can't attack the charmer; charmer has advantage on social checks."),
        ("deafened", "Can't hear and automatically fails hearing checks."),
        ("frightened", "Disadvantage while the source is in sight; can't move closer."),
        ("grappled", "Speed 0; ends if the grappler is incapacitated."),
        ("incapacitated", "Can't take actions or reactions."),
        ("invisible", "Unseen; attacks against have disadvantage, its attacks advantage."),
        ("paralyzed", "Incapacitated; auto-fails STR/DEX saves; hits within 5 ft are crits."),
        ("petrified", "Turned to stone; incapacitated and resistant to all damage."),
        ("poisoned", "Disadvantage on attack rolls and ability checks."),
        ("prone", "Disadvantage on attacks; melee against have advantage."),
        ("restrained", "Speed 0; disadvantage on attacks and DEX saves."),
        ("stunned", "Incapacitated; auto-fails STR/DEX saves."),
        ("unconscious", "Incapacitated, prone; auto-fails STR/DEX saves; hits are crits."),
        ("exhaustion", "Cumulative levels 1-6 imposing escalating penalties."),
    ]
]

_CHARACTER_LAYOUT: LayoutSpec = {
    "sections": [
        {
            "title": "Class & Level",
            "fields": [
                {"key": "class_name", "label": "Class", "role": "text"},
                {"key": "level", "label": "Level", "role": "number"},
            ],
        },
        {
            "title": "Vitals",
            "fields": [
                {"key": "max_hit_points", "label": "Max HP", "role": "number"},
                {"key": "current_hit_points", "label": "Current HP", "role": "number"},
                {"key": "armor_class", "label": "Armor Class", "role": "number"},
            ],
        },
        {
            "title": "Abilities",
            "fields": [{"key": "abilities", "label": "Abilities", "role": "ability-array",
                        "keys": list(_ABILITIES)}],
        },
        {"title": "Notes", "fields": [{"key": "notes", "label": "Notes", "role": "paragraph"}]},
    ]
}

_MONSTER_LAYOUT: LayoutSpec = {
    "sections": [
        {
            "title": "Overview",
            "fields": [
                {"key": "size", "label": "Size", "role": "text"},
                {"key": "type", "label": "Type", "role": "text"},
                {"key": "challenge_rating", "label": "CR", "role": "number"},
                {"key": "xp", "label": "XP", "role": "number"},
            ],
        },
        {
            "title": "Combat",
            "fields": [
                {"key": "armor_class", "label": "Armor Class", "role": "number"},
                {"key": "hit_points", "label": "Hit Points", "role": "number"},
                {"key": "speed", "label": "Speed", "role": "text"},
            ],
        },
        {
            "title": "Abilities",
            "fields": [{"key": "abilities", "label": "Abilities", "role": "ability-array",
                        "keys": list(_ABILITIES)}],
        },
    ]
}


def _mod(score: int) -> int:
    return (score - 10) // 2


def _proficiency_for_cr(cr: float) -> int:
    for threshold, bonus in _CR_PROFICIENCY:
        if cr <= threshold:
            return bonus
    return 9


class Dnd5eSystem(BaseRuleSystem):
    id = "dnd5e"
    name = "D&D 5e"
    version = "5.1.0"
    _schemas: ClassVar[dict[str, JsonSchema]] = {
        "pc": _CHARACTER_SCHEMA,
        "npc": _CHARACTER_SCHEMA,
        "monster": _MONSTER_SCHEMA,
    }

    def derive(self, sheet_type: str, doc: Document) -> dict[str, Any]:
        abilities = doc.get("abilities") or {}
        mods = {a: _mod(int(abilities.get(a, 10))) for a in _ABILITIES}
        if sheet_type == "monster":
            prof = _proficiency_for_cr(float(doc.get("challenge_rating", 0)))
            return {
                "ability_modifiers": mods,
                "proficiency_bonus": prof,
                "passive_perception": 10 + mods["wis"],
            }
        prof = 2 + (int(doc.get("level", 1)) - 1) // 4
        result: dict[str, Any] = {
            "ability_modifiers": mods,
            "proficiency_bonus": prof,
            "passive_perception": 10 + mods["wis"],
            "initiative": mods["dex"],
        }
        spell_ability = doc.get("spellcasting_ability")
        if spell_ability in _ABILITIES:
            result["spell_save_dc"] = 8 + prof + mods[spell_ability]
        return result

    def render_layout(self, sheet_type: str) -> LayoutSpec:
        self.sheet_schema(sheet_type)
        return _MONSTER_LAYOUT if sheet_type == "monster" else _CHARACTER_LAYOUT

    def conditions(self) -> list[ConditionDef]:
        return _CONDITIONS

    def facet_manifest(self) -> list[FacetDef]:
        return [
            {"key": "facet1_num", "label": "CR", "type": "number"},
            {"key": "facet2_num", "label": "XP", "type": "number"},
            {"key": "facet1_text", "label": "Type", "type": "text"},
            {"key": "facet2_text", "label": "Size", "type": "text"},
        ]

    def monster_facets(self, doc: Document) -> FacetValues:
        return {
            "facet1_num": float(doc.get("challenge_rating", 0)),
            "facet2_num": float(doc.get("xp", 0)),
            "facet1_text": str(doc.get("type", "")).lower(),
            "facet2_text": str(doc.get("size", "")),
        }

    def content_packs(self) -> list[ContentPack]:
        return [CONTENT_PACK]

    def _max_hp(self, sheet_type: str, doc: Document) -> int:
        # A 5e monster's HP lives under `hit_points`; a character's under `max_hit_points`.
        key = "hit_points" if sheet_type == "monster" else "max_hit_points"
        return int(doc.get(key, 0))

    def initial_status(
        self, sheet_type: str, doc: Document, hit_points: int | None = None
    ) -> Document:
        max_hp = self._max_hp(sheet_type, doc)
        return {
            "current_hit_points": max_hp if hit_points is None else hit_points,
            "conditions": [],
            "exhaustion": 0,
        }

    def combat_profile(
        self, sheet_type: str, doc: Document, status: Document | None = None
    ) -> CombatProfile:
        max_hp = self._max_hp(sheet_type, doc)
        abilities = doc.get("abilities") or {}
        return {
            "max_hp": max_hp,
            "hp": int((status or {}).get("current_hit_points", max_hp)),
            "initiative": _mod(int(abilities.get("dex", 10))),
        }

    def rest_types(self) -> list[str]:
        return ["short", "long"]

    def overnight_rest_type(self) -> str | None:
        return "long"

    def rest_duration_seconds(self, rest_type: str) -> int:
        return {"short": 3600, "long": 28800}.get(rest_type, 0)  # 1h / 8h

    def apply_rest(self, rest_type: str, status: Document, doc: Document) -> Document:
        new_status = dict(status)
        if rest_type == "long":
            # A long rest restores all lost hit points (SRD).
            new_status["current_hit_points"] = int(doc.get("max_hit_points", 0))
            new_status["exhaustion"] = max(0, int(status.get("exhaustion", 0)) - 1)
        return new_status

    def travel_pace_table(self) -> TravelPaceTable:
        """SRD 5.1 travel paces (PHB ch.8). Distances are *per day of travel* (8 hours).

        Terrain multipliers fold the "difficult terrain halves speed" rule into a single
        number per terrain, so the planner never needs to know 5e's vocabulary.
        """
        return {
            "supported": True,
            "distance_unit": "miles",
            "hours_per_travel_day": 8,
            "paces": {
                "slow": {"foot": 18, "horse": 30, "wagon": 16, "ship": 60},
                "normal": {"foot": 24, "horse": 40, "wagon": 20, "ship": 72},
                "fast": {"foot": 30, "horse": 50, "wagon": 24, "ship": 84},
            },
            "terrain": {
                "road": 1.0, "plains": 1.0, "hills": 0.75, "forest": 0.5,
                "mountains": 0.5, "swamp": 0.25, "sea": 1.0,
            },
            # Pushing past 8 hours of travel in a day risks exhaustion (forced march).
            "forced_march_after_seconds": 8 * 3600,
        }

    def round_length_seconds(self) -> int:
        return 6  # a 6-second round

    def encounter_difficulty(
        self, party: list[Document], foes: list[tuple[Document, int]]
    ) -> dict[str, Any]:
        thresholds = [0, 0, 0, 0]
        for pc in party:
            level = max(1, min(20, int(pc.get("level", 1))))
            for i, value in enumerate(_XP_THRESHOLDS[level]):
                thresholds[i] += value

        total_xp = sum(int(doc.get("xp", 0)) * count for doc, count in foes)
        num_monsters = sum(count for _doc, count in foes)
        adjusted = int(total_xp * _encounter_multiplier(num_monsters))

        easy, medium, hard, deadly = thresholds
        if not party or num_monsters == 0:
            rating = "none"
        elif adjusted >= deadly:
            rating = "deadly"
        elif adjusted >= hard:
            rating = "hard"
        elif adjusted >= medium:
            rating = "medium"
        elif adjusted >= easy:
            rating = "easy"
        else:
            rating = "trivial"

        return {
            "supported": True,
            "difficulty": rating,
            "total_xp": total_xp,
            "adjusted_xp": adjusted,
            "party_size": len(party),
            "thresholds": {"easy": easy, "medium": medium, "hard": hard, "deadly": deadly},
        }

    def skill_check_dcs(self) -> SkillCheckDcs:
        # The DMG "Typical Difficulty Classes" ladder (DMG p.238 / PHB p.174).
        return {
            "trivial": 5, "easy": 10, "normal": 15,
            "hard": 20, "very_hard": 25, "nearly_impossible": 30,
        }


SYSTEM = Dnd5eSystem()
