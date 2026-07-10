# 19. Future Enhancements (Post-1.0)

Ordered roughly by (persona demand × architectural readiness). Each item notes the seam that
was deliberately left for it — nothing here requires reworking the core.

## 19.1 AI features (the designed-for roadmap, ADR-012)

The substrate already exists: every domain event carries `narrative_text`, campaign
timestamps, session attribution, and entity references; sessions are bounded event windows;
`entity.article_text` is a clean plain-text corpus.

1. **Session recap generation.** Input: the session's ordered `narrative_text` stream +
   touched-entity summaries. Output: prose recap in selectable voices ("previously on…",
   player-facing summary, GM debrief) saved as a draft on the session for GM editing.
   Architecture: a new `ai` module calling a provider behind an interface (local or API,
   user-supplied key); no core changes — it is a *reader* of the event log.
2. **Timeline summarization.** Rolling arc summaries over event windows (act, month, whole
   campaign, per-entity biography — "the story of Serah Voss" from her `event_entity` slice).
   Same reader pattern; summaries stored as manual-style timeline entries flagged `generated`.
3. Later AI candidates (same substrate): NPC voice/behavior suggestions grounded in the
   NPC's article + history; consistency linting ("this NPC is referenced as dead in…");
   natural-language campaign queries compiled to the existing query surface.

Principles: AI output is always a *draft the GM edits*, never an autonomous world mutation;
providers are pluggable; nothing ships data anywhere without an explicit key + consent.

## 19.2 Shared campaigns & hosting (Persona P4)

Seams in place: `campaign_member` roles, `created_by` attribution everywhere, optimistic
versioning, campaign-scoped authz dependency, SSE design sketch (§13.4), PG-portable schema
(NFR-5.2). Work: real authentication UX, invitations, PostgreSQL port, hosted packaging
(container), conflict-surfacing UI. This is the largest single post-1.0 investment and the
trigger for the PG port (R-12).

## 19.3 World simulation depth

- **Shop inventories & economy:** `restock_shop` scheduled action graduates from narration to
  a real inventory model; price drift by region/season.
- **Faction simulation:** faction goals advance on time ticks (visible as proposed world
  events, GM-approved — consistent with the R-10 stance).
- **Downtime activity catalog:** per-system downtime rules via a new optional plugin method.
- **Weather:** calendar-driven generator (climate per region, season-aware), feeding travel
  modifiers — slots into `TravelPaceTable` as a multiplier source.

## 19.4 Story engine automation (FR-4.5 completion)

Event-pattern triggers with per-trigger opt-in auto-fire; trigger audit trail ("node activated
because…"); dry-run mode showing what *would* fire. The suggestions drawer already computes
the hard part (condition evaluation); this adds subscription + consent UX.

## 19.5 Wiki & knowledge depth

- Article **version history** with diffs and restore (snapshot table; audit events already
  mark the moments).
- **Entity templates** & bulk import (CSV/JSON) for established worlds — including a
  World Anvil / Obsidian-vault importer (mention syntax maps cleanly onto our links).
- **Whiteboard/relationship canvas:** free-form React Flow board over the existing
  neighborhood API for prep brainstorming.
- Cross-campaign **world reuse**: promote a world + its entities to a shared library
  installable into new campaigns (content-pack machinery generalizes here).

## 19.6 Play-surface extensions

- **Handout export:** render an entity/article to a printable/shareable PDF (the *only*
  player-touching artifact, and it leaves the app).
- **Companion tablet layout** for the dashboard (already responsive; this is polish +
  wake-lock + bigger touch targets).
- **Dice log & roller upgrade:** roll history as low-significance events, advantage/expr
  parser (UI-level; rules engine stays out of dice, §10.5).
- **Audio session notes:** local recording + timestamps aligned to the event stream (feeds
  AI recap quality enormously).

## 19.7 Platform & operability

- **Desktop packaging** (Tauri wrapping the local server) for a one-icon install.
- **Calendar editor UI** (FR-5.8 — the data model shipped in MVP).
- **Custom fields** per entity type per campaign (schema: `extras_json` columns already
  everywhere; this adds definition + form generation).
- **Plugin marketplace** for rules systems — explicitly requires a security story
  (sandboxing or review) per §14.4; not before demand proves itself.

## 19.8 Explicitly rejected (re-argue only with new evidence)

Player accounts / player views · real-time collaborative editing · VTT features of any kind ·
turning the story engine into an autonomous simulation that overrides GM authorship. These
are identity decisions from the PRD, not backlog items.
