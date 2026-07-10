# 15. Development Roadmap & 16. Sprint-by-Sprint Implementation Plan

Planning basis: **one experienced full-stack developer**, ~full-time, two-week sprints.
Estimates carry a solo-dev honesty margin (+30% vs. ideal) already baked in. The roadmap's
spine is: *prove the risky engines early, ship a usable wiki fast, add play tools before
polish*. Milestone definitions and deferral rationale live in
[MVP Definition](16-mvp-definition.md); the risk numbers reference the
[Risk Register](13-risk-register.md).

## 15.1 Phases

| Phase | Sprints | Outcome | Retires risks |
|---|---|---|---|
| 0 — Foundations | 1–2 | Walking skeleton: pipeline, registry, CI, typed client, shell | R-4, R-9 |
| 1 — The Wiki | 3–5 | Usable interconnected wiki with search (first dogfood-able build) | R-2 |
| 2 — The Clock & The Ledger | 6–8 | Time engine, domain events, timeline, sessions | R-1 |
| 3 — The Engine & The Bestiary | 9–11 | Rules plugin interface, 5e, stat blocks, monsters, party/PCs | R-3 |
| 4 — The Table | 12–14 | Encounters, combat tracker, live dashboard → **MVP** | R-5 |
| 5 — The Atlas & The Threads | 15–17 | Maps, quests-as-graph, NPC schedules/travel polish | R-6 |
| 6 — v1.0 Hardening | 18–20 | Nimble plugin, export/import, story graph, backups, docs | R-3, R-8 |

Dogfooding rule: from Sprint 5 onward, the developer runs a real campaign on the tool.
Every sprint review = one real prep session + (from Sprint 14) one real game session.

## 16. Sprint-by-Sprint Plan

Format: **Goal · Key work · Exit criteria** (exit criteria are demos, not task lists).

### Sprint 1 — Skeleton
Repo, tooling (ruff/mypy/eslint/tsc strict, pre-commit), FastAPI app, SQLAlchemy+Alembic,
SQLite setup (WAL, FK pragmas), command-pipeline context manager (§8.1) with `domain_event`
table, module layout + import-linter contracts, Vite/React shell with router + dark theme.
**Exit:** `POST /entities` (note type) → event row committed atomically; CI green; typed client
generated and consumed by a trivial page.

### Sprint 2 — Registry & campaign scaffolding
Entity registry CRUD + soft delete/restore, campaign/user/member tables with
`require_campaign_role`, campaign create/switch UI, tags, seed script (demo campaign).
**Exit:** create campaign → create entities of 3 types → tag, rename, delete/restore, all
scoped, all audited in the event log.

### Sprint 3 — Articles & mentions
Tiptap editor with `@mention` node (search-driven), article autosave/save, mention→link diff
sync, plain-text extraction, "missing entity" red links with create-in-place.
**Exit:** typing `@Bar` links an article to Barrow Tavern; deleting the mention removes the
link; red link creates & links a new entity without leaving the editor.

### Sprint 4 — Links, backlinks, entity pages
Typed relations editor, link_type dictionary, backlinks grouped by inverse label, location
`within` hierarchy + cycle guard + breadcrumbs, entity page layout (header/fields/article/
relations/referenced-by), browse hubs with filters.
**Exit:** Wikipedia-feel demo: navigate NPC→tavern→city→region purely by links/backlinks;
cycle insert rejected with a clear error.

### Sprint 5 — Search & command palette  ▶ *dogfooding begins*
FTS5 contentless index + sync in entity service, `/search` ranked API, ⌘K palette (results +
commands + recents), side-panel entity peek.
**Exit:** 5k-entity fixture searches in <100 ms; every entity reachable in ≤2 interactions
from anywhere (NFR-3.1 spot-check).

### Sprint 6 — Calendar math & clock
`CalendarMath` (Python) + presets (Harptos, Generic), property/golden tests, clock widget with
formatted date, manual advancement (`/clock/advance` manual+wait), `time_advanced` events,
TS port + parity fixtures.
**Exit:** advance across month/leap boundaries; widget and API agree with golden files.

### Sprint 7 — Scheduled events & the advancement loop
`scheduled_event` table, ordered firing loop with recurrence + runaway guard (§9.3),
`narrate`/`set_flag` actions, `AdvanceReport` toast digest, scheduled-events manager UI.
**Exit:** "advance 30 days" fires a weekly festival 4× in order, atomically; preview shows
what would fire before committing.

### Sprint 8 — Timeline & sessions
Timeline projection + manual lore entries + filters UI, session aggregate
(start/end/live-stamping), quick-notes capture, session auto-links view, projection-rebuild
CLI + consistency test harness.
**Exit:** run a fake session: events land in the live session; timeline filters by
session/entity/date; `rebuild-projections` output ≡ incremental tables.

### Sprint 9 — Rules plugin interface
`RuleSystem` protocol + types (§10.2), plugin discovery/registry, `simpletest` stub system,
`stat_block` storage + validate/derive round-trip, generic schema-driven sheet renderer v1.
**Exit:** create/edit a character in the stub system through the generic renderer; core has
zero 5e imports (lint-enforced).

### Sprint 10 — D&D 5e plugin (sheets & content)
5e schemas (PC/NPC/monster), derive (AC, DCs, passives), SRD content pack import
(copy-on-write), conditions catalog, bespoke 5e stat-block component.
**Exit:** browse SRD monsters; open a classic-styled stat block; validation rejects a bad doc
with field-level errors.

### Sprint 11 — Monsters, PCs, party
Monster browser with facet filters (manifest-driven), variants, PC records + party
(members/gold/inventory/reputation), rest commands via plugin (`apply_short/long_rest` →
status + clock).
**Exit:** long rest advances clock 8 h and restores party per 5e rules; filter monsters
CR 3–6 undead in <100 ms.

### Sprint 12 — Encounter builder
Encounter entity (combatants/terrain/hazards/tactics), difficulty via plugin vs. current
party, linking to locations/quests, encounter library UI.
**Exit:** build "Barrow Ambush", see difficulty badge, find it later from the location's page.

### Sprint 13 — Combat tracker
Combat action log + Python reducer + cursor undo/redo, TS reducer twin + parity fixtures,
tracker UI (initiative rail, cards, keypad, conditions, concentration, legendary/lair),
optimistic updates.
**Exit:** run a 4v6 fight entirely by keyboard; undo 10 steps and redo 3; refresh mid-combat
and resume exactly.

### Sprint 14 — Combat end & live dashboard  ▶ *first real session on the tool*
Combat summarization → domain events → timeline + clock advance; dashboard composite view +
panel grid (clock, party, quests, NPCs-here, encounters-near, tracker embed, pinned blocks,
notes, event feed); layout presets.
**Exit (= MVP exit):** run a full real game session start-to-finish on the dashboard without
opening another tool; timeline reads as the session's story afterwards.

### Sprint 15 — Maps I
Upload + server-side tiling pipeline (202 job), Leaflet CRS.Simple viewer, markers with
entity links + peek, free notes, edit/play modes.
**Exit:** 12k×12k map pans at 60 fps; clicking a marker peeks the NPC.

### Sprint 16 — Maps II & quest graph
Child-map markers + breadcrumb stack, marker layers/filters, polygon regions, quest DAG view
(React Flow + dagre) + deadline scheduled-events (auto-expire), quest board kanban.
**Exit:** world→city→tavern-map drill-down and back; quest expires when time passes its
deadline and the timeline says so.

### Sprint 17 — NPC dynamics
NPC location history UI ("where was X…?" query panel), `move_npc` scheduled actions, NPC
schedules (lazy materialization §9.6), travel planner (legs→preview→commit, auto rest stops),
`knows_about` queries.
**Exit:** demo the spec's query set: where is X now / where was X during session 7 / who knows
about the artifact / who has met the party / who is dead.

### Sprint 18 — Nimble plugin & second-system proof
Nimble schemas, rests, initiative, facets, content (as licensing allows); fix every 5e
assumption it flushes out; generic-renderer polish from the experience.
**Exit:** a Nimble campaign runs sheet→encounter→combat→rest end-to-end with core untouched.

### Sprint 19 — Data lifecycle
Full export/import (JSON+media archive, versioned manifest), automatic backup rotation
(+pre-migration, +session-start), delete-preflight references UI, article version snapshots
(lightweight), `SECURITY.md` + P-LAN recipe.
**Exit:** export → wipe → import → byte-identical projections after rebuild; restore from an
automatic backup in <2 minutes by following docs.

### Sprint 20 — Story graph & v1.0 hardening
Story nodes/edges editor (React Flow), condition DSL + validator + suggestions drawer,
consequences (closed action catalog), performance pass against NFR-1.6 fixture (50k entities),
accessibility pass, onboarding (5-minute first-campaign flow, NFR-3.5), docs site.
**Exit:** v1.0 tag. The IF-merchant-survives demo from the spec works via flags + suggestions;
NFR-1 numbers measured and recorded in CI.

## 16.1 Capacity & sequencing notes

- **Total: 20 sprints ≈ 10 months** full-time solo (MVP at Sprint 14 ≈ 7 months). If the
  developer is part-time (evenings/weekends at ~40%), calendar time ≈ 2× — plan morale
  accordingly: the Sprint-5 and Sprint-14 dogfood moments are the motivation anchors.
- The riskiest novel engineering (time engine, event pipeline) is deliberately in Sprints 1–8,
  before sunk-cost pressure builds; the most *replaceable* work (maps, story graph) is last.
- Each sprint ends with: migration review, `rebuild-projections` clean run on the dogfood
  campaign, and a tagged installable build.
