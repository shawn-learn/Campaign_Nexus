# 10. Rules Engine Architecture

Goal G6 / FR-11: support D&D 5e and Nimble at launch, add further systems with **zero core
schema changes**, and keep every game-system concept out of core code. Decision baseline:
ADR-010 (plugin packages + JSON-schema documents).

## 10.1 Architectural position

The rules engine is a **leaf module**: core modules call *into* it through a narrow interface;
it calls into nothing (no DB access except reading its own content packs at import time). All
system-specific persistence is opaque JSON (`stat_block.doc_json`) that only the owning plugin
interprets.

```
 Combat ─┐                       ┌─ dnd5e plugin (schemas, logic, content packs)
 Time   ─┤→  RuleSystem API  ──► ├─ nimble plugin
 Quests ─┤   (abstract iface)    └─ future plugins…
 Sheets ─┘
```

## 10.2 The `RuleSystem` interface (conceptual signature)

```python
class RuleSystem(Protocol):
    id: str                      # 'dnd5e'
    name: str
    version: str                 # plugin semver; schema_version stamped on documents

    # -- documents ---------------------------------------------------------
    def sheet_schema(self, sheet_type: SheetType) -> JsonSchema: ...
    def validate(self, sheet_type, doc) -> list[ValidationError]: ...
    def derive(self, sheet_type, doc) -> dict:
        """Computed values (AC, save DCs, passive perception…) → stat_block.derived_json"""
    def render_layout(self, sheet_type) -> LayoutSpec:
        """Declarative UI hints: sections, field order, dice-notation fields (see §10.5)"""
    def migrate_doc(self, sheet_type, doc, from_version) -> dict: ...

    # -- play mechanics ----------------------------------------------------
    def conditions(self) -> list[ConditionDef]          # name, icon, description, stacking
    def initiative(self, doc) -> InitiativeSpec         # bonus, tiebreak rule
    def round_length_minutes(self) -> float             # 5e: 0.1 (6 s)
    def apply_short_rest(self, pc_status, doc) -> StatusDelta
    def apply_long_rest(self, pc_status, doc) -> StatusDelta
    def travel_paces(self) -> TravelPaceTable           # speeds, conveyances, terrain multipliers
    def encounter_difficulty(self, party: list[doc], foes: list[(doc, count)]) -> DifficultyReport
    def monster_facets(self, doc) -> FacetValues        # populates monster.facet* columns
    def facet_manifest(self) -> list[FacetDef]          # tells the UI what facets mean (CR, type…)

    # -- content -----------------------------------------------------------
    def content_packs(self) -> list[ContentPack]        # bundled monsters/items as JSON
```

Interface rules:
- **Pure functions over documents.** No plugin touches the database or the event log; core
  calls it and records results. This makes plugins trivially unit-testable and sandboxable.
- **Everything optional degrades.** A plugin may return "not supported" for e.g.
  `encounter_difficulty`; the UI hides the estimate rather than breaking (Nimble ships before
  its difficulty model is polished).
- Discovery via Python entry points (`campaign_nexus.rule_systems`); installed plugins
  register rows in `rule_system`.

## 10.3 Document model

- One `stat_block` row per sheet: `doc_json` (authored data) + `derived_json` (plugin-computed
  cache, refreshed on every doc write).
- Docs validate against the plugin's **JSON Schema** on every write; invalid writes are
  rejected with field-level errors surfaced in the sheet editor.
- `schema_version` pins the document; on plugin upgrade, `migrate_doc` lazily upcasts on first
  write (reads tolerate old versions via the plugin's read path).
- **Live status is separate from the sheet.** `pc.status_json` (current HP, slot usage,
  conditions, exhaustion) is mutable play-state shaped by the plugin (`StatusDelta` contract);
  the stat block is the character's *definition*. Rest commands and combat write status, not docs.

## 10.4 Facets: querying inside opaque documents

Core cannot filter on "CR ≥ 5" without knowing 5e — so it doesn't. Each plugin maps up to four
**facet columns** on `monster` (2 numeric, 2 text) via `monster_facets()`, and describes them
via `facet_manifest()` (name, type, filter widget). 5e: `CR`, `XP`, `creature type`, `size`.
Nimble: its own. The monster browser renders filter controls from the manifest — fully generic
UI, indexed SQL filtering, zero schema coupling. (Four columns is a deliberate sufficiency
bet; a fifth facet would be an additive migration.)

## 10.5 Stat-block rendering (FR-11.5)

Two-tier strategy:

1. **Schema-driven renderer (default).** `render_layout()` returns a declarative `LayoutSpec`
   — sections, rows, field references, display roles (`heading`, `ability-array`, `dice`,
   `trait-list`, `paragraph`). A generic React component renders any system acceptably. This
   is the guarantee that a new plugin gets working sheets with zero frontend work.
2. **Bespoke component (optional polish).** The frontend keeps a registry
   `system_id → React component`; when present it overrides the generic renderer. 5e ships
   with a bespoke, classic-stat-block-styled component; Nimble launches on the generic
   renderer.

Dice notation fields (`1d8+3`) are declared by role; the UI renders them as clickable rollers
(local roll, result to the session note stream) — rolling is a UI affordance, not a rules-
engine responsibility.

## 10.6 Content packs

- A pack = JSON manifest + documents (monsters, items), shipped inside the plugin wheel.
  5e ships the SRD 5.1 pack (CC-BY-4.0 — attribution rendered in-app; see Risk R-7).
- Import materializes pack content as shared rows (`stat_block.campaign_id NULL`) referenced
  by campaigns; **copy-on-write**: customizing a pack monster clones it into the campaign as a
  variant (`monster.variant_of`), preserving the pristine original.
- Packs are versioned; upgrades never mutate campaign copies.

## 10.7 The two launch systems

| Concern | D&D 5e plugin | Nimble plugin |
|---|---|---|
| Sheets | full PC/NPC/monster schemas (abilities, skills, spellcasting, legendary/lair) | Nimble's lighter stat model |
| Conditions | 15 standard conditions + exhaustion levels | Nimble condition set |
| Rests | short 60 min / long 480 min; hit dice, slots, exhaustion | Nimble rest economy |
| Initiative | DEX-based d20, plugin tiebreak | Nimble initiative rules |
| Difficulty | XP-threshold encounter math | simpler heuristic (or "unsupported" at launch) |
| Facets | CR / XP / type / size | level / role equivalents |
| Content | SRD monsters & items | Nimble core content (license permitting; else schema + empty pack) |

Nimble's strategic role is **architecture validation**: it is different enough (no
Vancian slots, different rest/initiative economy) that any 5e assumption leaking into core
surfaces immediately. MVP builds the interface + 5e + a CI-only `simpletest` stub system
(minimal schemas) as the honesty check; Nimble completes in v1.0 (see MVP definition).

**As built (Sprint 18).** `app.modules.rules.systems.nimble` ships schemas only — no content
pack, no rules text (licensing). Four attributes stored as modifiers, armor as an enum,
`max_hp` rather than `max_hit_points`, monsters rated by level + role, `field`/`safe` rests,
and no travel table (so the planner returns 501 instead of inventing miles). It flushed out
five 5e assumptions, all now fixed:

1. the combat tracker read `hit_points`/`max_hit_points` straight out of a stat block;
2. `add_member` invented a `{"current_hit_points": …}` status document;
3. `RestRequest` pinned the rest name to a `^(short|long)$` regex;
4. the travel planner asked for the `"long"` rest by name;
5. the timeline catalog enumerated `long_rest_completed`, and the generic sheet renderer
   hardcoded 5e's six abilities.

The fixes added three interface methods — `initial_status`, `combat_profile` and
`overnight_rest_type` — so the playbook now asks the plugin for HP, initiative and the shape
of live play-state instead of reading the document. Nimble's "the party acts first" rule
needs no core concept: it simply returns a higher `initiative` for characters than for
monsters, and the tracker's existing descending sort does the rest. An `ability-array` layout
field now carries its own `keys`, which the conformance kit asserts for every system.

## 10.8 What core knows about game systems

The complete list — anything beyond this is a design violation caught in review:
`SheetType` enum, the `RuleSystem` interface types (`StatusDelta`, `TravelPaceTable`,
`DifficultyReport`, `ConditionDef`, `InitiativeSpec`, `FacetDef`, `LayoutSpec`), and the fact
that campaigns bind to exactly one `rule_system_id`. Core never mentions HP formulas, spell
slots, CR, or any 5e/Nimble noun.
