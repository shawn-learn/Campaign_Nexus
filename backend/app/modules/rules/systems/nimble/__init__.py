"""Nimble — the second-system proof (docs/08 §10.7, roadmap Sprint 18).

This is a *community approximation* of the Nimble ruleset's shape, not a licensed SRD port:
it ships **no content pack** (no monsters, no spells, no rules text). What matters here is
that it disagrees with D&D 5e everywhere it can, so any 5e assumption still hiding in core
fails loudly:

===================  =========================  ==============================
                     D&D 5e                     Nimble
===================  =========================  ==============================
abilities            six (str…cha), scores      four (str/dex/int/wil), *modifiers*
defence              armor class (a number)     armor category (an enum)
hp key               ``max_hit_points``         ``max_hp``
monster rating       challenge rating + XP      level + role
initiative           roll d20 + dex             none — the party acts first
rests                short (1h) / long (8h)     field (1h) / safe (overnight)
travel               miles/day pace table       not modelled
===================  =========================  ==============================

The last row is the point of ``travel_pace_table`` returning ``{"supported": False}``: the
planner must degrade to a 501, not invent miles.
"""

from __future__ import annotations

from typing import Any, ClassVar

from app.modules.rules.interface import (
    BaseRuleSystem,
    CombatProfile,
    ConditionDef,
    Document,
    FacetDef,
    FacetValues,
    JsonSchema,
    LayoutSpec,
    SkillCheckDcs,
)

#: Nimble's four attributes. They are stored as modifiers, not 3-18 scores.
_ATTRIBUTES = ("str", "dex", "int", "wil")
_ARMOR = ["none", "light", "medium", "heavy"]
#: Armor category -> the damage it turns aside each hit.
_ARMOR_VALUE = {"none": 0, "light": 1, "medium": 2, "heavy": 3}
_ROLES = ["minion", "standard", "elite", "solo"]

_attributes_schema: JsonSchema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {a: {"type": "integer", "minimum": -3, "maximum": 10} for a in _ATTRIBUTES},
}

_CHARACTER_SCHEMA: JsonSchema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "class_name": {"type": "string"},
        "level": {"type": "integer", "minimum": 1, "maximum": 20},
        "max_hp": {"type": "integer", "minimum": 1},
        "hit_dice": {"type": "string"},
        "armor": {"type": "string", "enum": _ARMOR},
        "attributes": _attributes_schema,
        "notes": {"type": "string"},
    },
    "required": ["level", "max_hp", "armor", "attributes"],
}

_MONSTER_SCHEMA: JsonSchema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "level": {"type": "integer", "minimum": 0, "maximum": 20},
        "role": {"type": "string", "enum": _ROLES},
        "kind": {"type": "string"},
        "size": {"type": "string"},
        "max_hp": {"type": "integer", "minimum": 1},
        "armor": {"type": "string", "enum": _ARMOR},
        "attributes": _attributes_schema,
        "notes": {"type": "string"},
    },
    "required": ["level", "role", "max_hp", "armor"],
}

_CHARACTER_LAYOUT: LayoutSpec = {
    "sections": [
        {
            "title": "Character",
            "fields": [
                {"key": "class_name", "label": "Class", "role": "text"},
                {"key": "level", "label": "Level", "role": "number"},
                {"key": "max_hp", "label": "Max HP", "role": "number"},
                {"key": "hit_dice", "label": "Hit Dice", "role": "dice"},
                {"key": "armor", "label": "Armor", "role": "text"},
            ],
        },
        {
            "title": "Attributes",
            "fields": [{"key": "attributes", "label": "Attributes", "role": "ability-array",
                        "keys": list(_ATTRIBUTES)}],
        },
        {"title": "Notes", "fields": [{"key": "notes", "label": "Notes", "role": "paragraph"}]},
    ]
}

_MONSTER_LAYOUT: LayoutSpec = {
    "sections": [
        {
            "title": "Statistics",
            "fields": [
                {"key": "level", "label": "Level", "role": "number"},
                {"key": "role", "label": "Role", "role": "text"},
                {"key": "kind", "label": "Kind", "role": "text"},
                {"key": "size", "label": "Size", "role": "text"},
                {"key": "max_hp", "label": "Max HP", "role": "number"},
                {"key": "armor", "label": "Armor", "role": "text"},
            ],
        },
        {
            "title": "Attributes",
            "fields": [{"key": "attributes", "label": "Attributes", "role": "ability-array",
                        "keys": list(_ATTRIBUTES)}],
        },
        {"title": "Notes", "fields": [{"key": "notes", "label": "Notes", "role": "paragraph"}]},
    ]
}

_CONDITIONS: list[ConditionDef] = [
    {"id": "blinded", "name": "Blinded", "description": "Cannot see; attacks are hindered."},
    {"id": "charmed", "name": "Charmed", "description": "Cannot harm the charmer."},
    {"id": "dazed", "name": "Dazed", "description": "May only take one action."},
    {"id": "frightened", "name": "Frightened", "description": "Cannot approach the source."},
    {"id": "grappled", "name": "Grappled", "description": "Speed is zero."},
    {"id": "prone", "name": "Prone", "description": "Attacks against you are advantaged."},
    {"id": "restrained", "name": "Restrained", "description": "Cannot move; attacks hindered."},
    {"id": "slowed", "name": "Slowed", "description": "Half movement."},
    {"id": "stunned", "name": "Stunned", "description": "Cannot act."},
    {"id": "taunted", "name": "Taunted", "description": "Must target the taunter."},
]

#: A standard monster of level L is worth roughly L "encounter points"; the budget is the
#: party's total levels. Roles scale a monster's weight (a solo is a whole encounter).
_ROLE_WEIGHT = {"minion": 0.25, "standard": 1.0, "elite": 2.0, "solo": 4.0}
_BANDS = ((0.5, "trivial"), (0.85, "easy"), (1.15, "medium"), (1.6, "hard"))


class NimbleSystem(BaseRuleSystem):
    id = "nimble"
    name = "Nimble (community approximation)"
    version = "0.1.0"
    _schemas: ClassVar[dict[str, JsonSchema]] = {
        "pc": _CHARACTER_SCHEMA,
        "npc": _CHARACTER_SCHEMA,
        "monster": _MONSTER_SCHEMA,
    }

    # -- documents ---------------------------------------------------------
    def derive(self, sheet_type: str, doc: Document) -> dict[str, Any]:
        armor = str(doc.get("armor", "none"))
        derived: dict[str, Any] = {"armor_value": _ARMOR_VALUE.get(armor, 0)}
        attributes = doc.get("attributes") or {}
        if sheet_type == "monster":
            role = str(doc.get("role", "standard"))
            derived["encounter_weight"] = _ROLE_WEIGHT.get(role, 1.0) * int(doc.get("level", 0))
            return derived
        # Attributes *are* modifiers; no score-to-modifier arithmetic exists in Nimble.
        derived["attribute_modifiers"] = {a: int(attributes.get(a, 0)) for a in _ATTRIBUTES}
        derived["saving_throws"] = derived["attribute_modifiers"]
        return derived

    def render_layout(self, sheet_type: str) -> LayoutSpec:
        self.sheet_schema(sheet_type)  # unknown sheet types raise consistently
        return _MONSTER_LAYOUT if sheet_type == "monster" else _CHARACTER_LAYOUT

    def conditions(self) -> list[ConditionDef]:
        return _CONDITIONS

    # -- bestiary ----------------------------------------------------------
    def facet_manifest(self) -> list[FacetDef]:
        return [
            {"key": "facet1_num", "label": "Level", "type": "number"},
            {"key": "facet1_text", "label": "Kind", "type": "text"},
            {"key": "facet2_text", "label": "Role", "type": "text"},
        ]

    def monster_facets(self, doc: Document) -> FacetValues:
        return {
            "facet1_num": float(doc.get("level", 0)),
            "facet1_text": str(doc.get("kind", "")).lower(),
            "facet2_text": str(doc.get("role", "")),
        }

    # -- live play ---------------------------------------------------------
    def initial_status(
        self, sheet_type: str, doc: Document, hit_points: int | None = None
    ) -> Document:
        max_hp = int(doc.get("max_hp", 0))
        return {"hp": max_hp if hit_points is None else hit_points, "conditions": []}

    def combat_profile(
        self, sheet_type: str, doc: Document, status: Document | None = None
    ) -> CombatProfile:
        max_hp = int(doc.get("max_hp", 0))
        return {
            "max_hp": max_hp,
            "hp": int((status or {}).get("hp", max_hp)),
            # Nimble rolls no initiative: the party acts, then the monsters do. The tracker
            # orders by initiative descending, so this ranking *is* the rule.
            "initiative": 1 if sheet_type in ("pc", "npc") else 0,
            # No armour class to hit: Nimble's armour turns aside damage on a hit (see
            # ``_ARMOR_VALUE``), so there is no target number and nothing to compare a roll
            # against. ``initiative_dice: None`` says the same about order — there is no die
            # to roll, so the tracker must leave the ranking above alone.
            "ac": None,
            "initiative_dice": None,
            "initiative_mod": 0,
        }

    def with_hit_points(self, status: Document, doc: Document, hit_points: int) -> Document:
        new_status = dict(status)
        new_status["hp"] = max(0, int(hit_points))  # `hp`, not 5e's `current_hit_points`
        return new_status

    # -- rests -------------------------------------------------------------
    def rest_types(self) -> list[str]:
        return ["field", "safe"]

    def overnight_rest_type(self) -> str | None:
        return "safe"

    def rest_duration_seconds(self, rest_type: str) -> int:
        return {"field": 3600, "safe": 28800}.get(rest_type, 0)

    def apply_rest(self, rest_type: str, status: Document, doc: Document) -> Document:
        new_status = dict(status)
        if rest_type == "safe":
            # A safe rest returns you to full and clears what ails you.
            new_status["hp"] = int(doc.get("max_hp", 0))
            new_status["conditions"] = []
        return new_status

    # -- encounters --------------------------------------------------------
    def encounter_difficulty(
        self, party: list[Document], foes: list[tuple[Document, int]]
    ) -> dict[str, Any]:
        if not party or not foes:
            return {"supported": False}
        budget = sum(int(pc.get("level", 1)) for pc in party)
        weight = sum(
            _ROLE_WEIGHT.get(str(foe.get("role", "standard")), 1.0) * int(foe.get("level", 0)) * n
            for foe, n in foes
        )
        ratio = weight / budget if budget else 0.0
        difficulty = "deadly"
        for limit, band in _BANDS:
            if ratio <= limit:
                difficulty = band
                break
        return {
            "supported": True,
            "difficulty": difficulty,
            "total_xp": round(weight),  # Nimble has no XP; the generic field carries weight
            "adjusted_xp": round(weight),
            "party_size": len(party),
            "thresholds": {band: round(budget * limit) for limit, band in _BANDS},
        }

    # -- skill challenges --------------------------------------------------
    def skill_check_dcs(self) -> SkillCheckDcs:
        # Nimble's DC ladder is compressed relative to 5e (10 / 15 / 20 are its common
        # targets), so an identical challenge authoring reads as different numbers here —
        # exactly the second-system divergence this plugin exists to prove.
        return {
            "trivial": 5, "easy": 10, "normal": 12,
            "hard": 15, "very_hard": 18, "nearly_impossible": 20,
        }


SYSTEM = NimbleSystem()
