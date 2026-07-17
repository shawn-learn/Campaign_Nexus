"""The ``RuleSystem`` plugin interface (docs/08, §10.2).

Sprint 9 ships the document-facing subset needed to author character sheets through the
generic renderer: schema, validate, derive, layout. Play-mechanics methods (conditions,
rests, travel, initiative, difficulty, facets, content packs) are added in later sprints.

Plugins are pure functions over documents — no database or event-log access — which keeps
them trivially testable and prevents any game system from leaking into the core.
"""

from __future__ import annotations

from typing import Any, ClassVar, Protocol, runtime_checkable

JsonSchema = dict[str, Any]
Document = dict[str, Any]
LayoutSpec = dict[str, Any]  # {"sections": [{"title", "fields": [{"key","label","role"}]}]}
ConditionDef = dict[str, Any]  # {"id","name","description"}
FacetDef = dict[str, Any]  # {"key": "facet1_num"|..., "label", "type": "number"|"text"}
FacetValues = dict[str, Any]  # {"facet1_num","facet2_num","facet1_text","facet2_text"}
ContentPack = dict[str, Any]  # {"id","version","attribution","monsters": [{"name","doc"}]}
# {"supported", "distance_unit", "paces": {pace: {conveyance: distance_per_day}},
#  "terrain": {terrain: multiplier}, "forced_march_after_seconds": int|None}
TravelPaceTable = dict[str, Any]
# Everything the combat tracker needs to seed a combatant. The playbook reads *this*, never
# the stat-block document (docs/04 §6.8):
#   max_hp, hp, initiative  — as before; ``initiative`` is the pre-roll seed / static ranking.
#   ac              — the number an attack must meet to hit, or None if the system has no
#                     such concept (Nimble's armour reduces damage; it is not a target).
#                     A None ac means the tracker reports the roll and lets the GM judge.
#   initiative_dice — the die initiative is rolled on ("1d20"), or None if the system does
#                     not roll for it at all — in which case ``initiative`` above already
#                     *is* the order and the tracker must not offer to roll.
#   initiative_mod  — what's added to that die, and the tiebreak between equal initiatives.
#   legendary       — legendary actions per round, or 0 for a creature that has none.
CombatProfile = dict[str, Any]
# Ordered {tier: dc} — how a system prices skill-challenge difficulty tiers as concrete
# target numbers. The skill-challenge feature is system-agnostic; this is its one hook into
# the rules plugin so a "hard" check means DC 20 in 5e but whatever Nimble calls hard.
SkillCheckDcs = dict[str, int]

# The canonical difficulty ladder skill challenges author against. Systems price each tier
# via ``skill_check_dcs``; unpriced systems fall back to the generic ladder in Base.
DIFFICULTY_TIERS = ("trivial", "easy", "normal", "hard", "very_hard", "nearly_impossible")

# Display roles the generic renderer understands.
FIELD_ROLES = (
    "text", "paragraph", "number", "boolean", "ability-array", "dice", "trait-list",
    "attack-list",
)

# What a creature can do on its turn, *resolved*: every number already summed, every damage
# expression already a rollable string. A system may author attacks however it likes — 5e
# lets a PC name an ability and a proficiency and derives the rest — but ``attack_actions``
# hands back only finished numbers, so the playbook rolls dice without knowing any rules.
#   {"name", "kind": "melee"|"ranged"|"save", "to_hit": int|None,
#    "reach", "target", "damage": [{"dice", "type"}],
#    "save": {"ability", "dc", "half_on_success"} | None,
#    "description", "crit_rule": "double_dice"|None}
AttackAction = dict[str, Any]

# How a system handles a creature at 0 hit points, or ``{"supported": False}`` if it has no
# such mechanic — the tracker then shows no death-save row at all rather than invent one.
#   {"supported": True, "dice": "1d20", "dc": 10, "successes": 3, "failures": 3}
# The reducer only counts; what a count *means* (stable, dead) is priced here, so 5e's
# three-and-three never gets hard-coded into a system-agnostic module.
DeathSaveRules = dict[str, Any]

# The four generic facet columns on the monster table (docs/08, §10.4).
FACET_KEYS = ("facet1_num", "facet2_num", "facet1_text", "facet2_text")


@runtime_checkable
class RuleSystem(Protocol):
    id: str
    name: str
    version: str

    def sheet_types(self) -> list[str]: ...
    def sheet_schema(self, sheet_type: str) -> JsonSchema: ...
    def validate(self, sheet_type: str, doc: Document) -> list[str]: ...
    def derive(self, sheet_type: str, doc: Document) -> dict[str, Any]: ...
    def render_layout(self, sheet_type: str) -> LayoutSpec: ...

    # -- play data (optional; Base returns empties) ------------------------
    def conditions(self) -> list[ConditionDef]: ...
    def facet_manifest(self) -> list[FacetDef]: ...
    def monster_facets(self, doc: Document) -> FacetValues: ...
    def content_packs(self) -> list[ContentPack]: ...

    # -- live play state (docs/04, §6.8: no other context reads inside a doc) -
    def initial_status(
        self, sheet_type: str, doc: Document, hit_points: int | None = None
    ) -> Document: ...
    def combat_profile(
        self, sheet_type: str, doc: Document, status: Document | None = None
    ) -> CombatProfile: ...
    def with_hit_points(
        self, status: Document, doc: Document, hit_points: int
    ) -> Document: ...
    def attack_actions(self, sheet_type: str, doc: Document) -> list[AttackAction]: ...
    def death_save_rules(self) -> DeathSaveRules: ...

    # -- rests (docs/08, §10.2) --------------------------------------------
    def rest_types(self) -> list[str]: ...
    def rest_duration_seconds(self, rest_type: str) -> int: ...
    def apply_rest(self, rest_type: str, status: Document, doc: Document) -> Document: ...
    #: The rest a multi-day journey stops for overnight; ``None`` = the system has no such rest.
    def overnight_rest_type(self) -> str | None: ...

    # -- travel (docs/07, §9.5) --------------------------------------------
    def travel_pace_table(self) -> TravelPaceTable: ...

    # -- encounters --------------------------------------------------------
    def round_length_seconds(self) -> int: ...
    def encounter_difficulty(
        self, party: list[Document], foes: list[tuple[Document, int]]
    ) -> dict[str, Any]: ...

    # -- skill challenges --------------------------------------------------
    def skill_check_dcs(self) -> SkillCheckDcs: ...


class UnknownSheetType(ValueError):
    pass


class BaseRuleSystem:
    """Convenience base: JSON-Schema validation from ``_schemas``; subclasses add derive/layout.

    Uses jsonschema Draft 2020-12. ``derive`` defaults to no computed values; ``render_layout``
    must be provided by the subclass.
    """

    id: str = ""
    name: str = ""
    version: str = "0.0.0"
    _schemas: ClassVar[dict[str, JsonSchema]] = {}

    def sheet_types(self) -> list[str]:
        return list(self._schemas)

    def sheet_schema(self, sheet_type: str) -> JsonSchema:
        if sheet_type not in self._schemas:
            raise UnknownSheetType(sheet_type)
        return self._schemas[sheet_type]

    def validate(self, sheet_type: str, doc: Document) -> list[str]:
        # Imported lazily so the dependency stays inside the rules module.
        from jsonschema import Draft202012Validator

        validator = Draft202012Validator(self.sheet_schema(sheet_type))
        errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
        return [f"{'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}" for e in errors]

    def derive(self, sheet_type: str, doc: Document) -> dict[str, Any]:
        return {}

    def render_layout(self, sheet_type: str) -> LayoutSpec:  # pragma: no cover - overridden
        raise NotImplementedError

    def conditions(self) -> list[ConditionDef]:
        return []

    def facet_manifest(self) -> list[FacetDef]:
        return []

    def monster_facets(self, doc: Document) -> FacetValues:
        return {}

    def content_packs(self) -> list[ContentPack]:
        return []

    def initial_status(
        self, sheet_type: str, doc: Document, hit_points: int | None = None
    ) -> Document:
        return {}

    def combat_profile(
        self, sheet_type: str, doc: Document, status: Document | None = None
    ) -> CombatProfile:
        # A system that ships no combat model still yields a well-formed combatant: no AC to
        # hit, no die to roll for order. The tracker degrades to a manual list, not an error.
        return {
            "max_hp": 0, "hp": 0, "initiative": 0,
            "ac": None, "initiative_dice": None, "initiative_mod": 0,
            "legendary": 0,
        }

    def with_hit_points(self, status: Document, doc: Document, hit_points: int) -> Document:
        # The write half of ``combat_profile``'s read: that method pulls live HP *out* of a
        # status; this one puts it back after combat, without disturbing anything else in
        # there (conditions, exhaustion). A system with no HP model writes nothing.
        return dict(status)

    def attack_actions(self, sheet_type: str, doc: Document) -> list[AttackAction]:
        # A system with no attack model offers nothing to click; the tracker just doesn't
        # show an attack panel. Same shape as every other optional hook: empty, not an error.
        return []

    def death_save_rules(self) -> DeathSaveRules:
        # No death saves here — the tracker shows no row rather than guessing at one.
        return {"supported": False}

    def rest_types(self) -> list[str]:
        return []

    def rest_duration_seconds(self, rest_type: str) -> int:
        return 0

    def apply_rest(self, rest_type: str, status: Document, doc: Document) -> Document:
        return status

    def overnight_rest_type(self) -> str | None:
        return None

    def travel_pace_table(self) -> TravelPaceTable:
        return {"supported": False}

    def round_length_seconds(self) -> int:
        return 6  # a 6-second round, the common default

    def encounter_difficulty(
        self, party: list[Document], foes: list[tuple[Document, int]]
    ) -> dict[str, Any]:
        return {"supported": False}

    def skill_check_dcs(self) -> SkillCheckDcs:
        # A generic d20-ish ladder over ``DIFFICULTY_TIERS``; systems with their own maths
        # (5e's DMG ladder, Nimble's compressed one) override this.
        return {
            "trivial": 5, "easy": 10, "normal": 15,
            "hard": 20, "very_hard": 25, "nearly_impossible": 30,
        }
