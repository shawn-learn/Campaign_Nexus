"""A minimal stub rule system (docs/08, §10.7).

Its only job is to prove the plugin interface is system-agnostic: it is different enough
from D&D 5e that any 5e assumption leaking into core surfaces immediately (mitigates R-3).
It ships in every build and is exercised by the plugin conformance kit in CI.
"""

from __future__ import annotations

from typing import Any, ClassVar

from app.modules.rules.interface import (
    BaseRuleSystem,
    CombatProfile,
    Document,
    JsonSchema,
    LayoutSpec,
)

_ABILITIES = ("str", "dex", "con", "int", "wis", "cha")

_CHARACTER_SCHEMA: JsonSchema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "level": {"type": "integer", "minimum": 1, "maximum": 20},
        "hit_points": {"type": "integer", "minimum": 1},
        "armor_class": {"type": "integer", "minimum": 0},
        "abilities": {
            "type": "object",
            "additionalProperties": False,
            "properties": {a: {"type": "integer", "minimum": 1, "maximum": 30} for a in _ABILITIES},
        },
        "notes": {"type": "string"},
    },
    "required": ["level", "hit_points", "armor_class"],
}

_MONSTER_SCHEMA: JsonSchema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "threat": {"type": "integer", "minimum": 0, "maximum": 30},
        "hit_points": {"type": "integer", "minimum": 1},
        "armor_class": {"type": "integer", "minimum": 0},
        "notes": {"type": "string"},
    },
    "required": ["threat", "hit_points"],
}

_CHARACTER_LAYOUT: LayoutSpec = {
    "sections": [
        {
            "title": "Vitals",
            "fields": [
                {"key": "level", "label": "Level", "role": "number"},
                {"key": "hit_points", "label": "Hit Points", "role": "number"},
                {"key": "armor_class", "label": "Armor Class", "role": "number"},
            ],
        },
        {
            "title": "Abilities",
            "fields": [{"key": "abilities", "label": "Abilities", "role": "ability-array",
                        "keys": list(_ABILITIES)}],
        },
        {
            "title": "Notes",
            "fields": [{"key": "notes", "label": "Notes", "role": "paragraph"}],
        },
    ]
}

_MONSTER_LAYOUT: LayoutSpec = {
    "sections": [
        {
            "title": "Stats",
            "fields": [
                {"key": "threat", "label": "Threat", "role": "number"},
                {"key": "hit_points", "label": "Hit Points", "role": "number"},
                {"key": "armor_class", "label": "Armor Class", "role": "number"},
                {"key": "notes", "label": "Notes", "role": "paragraph"},
            ],
        }
    ]
}


class SimpleTestSystem(BaseRuleSystem):
    id = "simpletest"
    name = "Simple Test System"
    version = "1.0.0"
    _schemas: ClassVar[dict[str, JsonSchema]] = {
        "pc": _CHARACTER_SCHEMA,
        "npc": _CHARACTER_SCHEMA,
        "monster": _MONSTER_SCHEMA,
    }

    def derive(self, sheet_type: str, doc: Document) -> dict[str, Any]:
        if sheet_type == "monster":
            threat = int(doc.get("threat", 0))
            return {"power_level": threat * 5 + int(doc.get("hit_points", 0)) // 10}
        level = int(doc.get("level", 1))
        hp = int(doc.get("hit_points", 0))
        return {
            "power_level": level + hp // 10,
            "proficiency_bonus": 2 + (level - 1) // 4,
        }

    def render_layout(self, sheet_type: str) -> LayoutSpec:
        # Touch the schema so an unknown sheet type raises consistently.
        self.sheet_schema(sheet_type)
        return _MONSTER_LAYOUT if sheet_type == "monster" else _CHARACTER_LAYOUT

    # Every sheet type here keys HP as `hit_points` and live HP as `hp` — deliberately
    # unlike 5e, so a playbook that reads `max_hit_points` directly breaks loudly.
    def initial_status(
        self, sheet_type: str, doc: Document, hit_points: int | None = None
    ) -> Document:
        max_hp = int(doc.get("hit_points", 0))
        return {"hp": max_hp if hit_points is None else hit_points}

    def combat_profile(
        self, sheet_type: str, doc: Document, status: Document | None = None
    ) -> CombatProfile:
        max_hp = int(doc.get("hit_points", 0))
        return {
            "max_hp": max_hp,
            "hp": int((status or {}).get("hp", max_hp)),
            "initiative": 0,  # this system has no initiative; insertion order wins
            # No AC, and no die to roll for order — same as the two above.
            "ac": None,
            "initiative_dice": None,
            "initiative_mod": 0,
            "legendary": 0,
            "spell_pools": {},  # no spellcasting model here either
        }

    def with_hit_points(self, status: Document, doc: Document, hit_points: int) -> Document:
        new_status = dict(status)
        new_status["hp"] = max(0, int(hit_points))
        return new_status


SYSTEM = SimpleTestSystem()
