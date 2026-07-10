# MVP Definition & Milestones

**Constraint:** one experienced developer · React + TypeScript · FastAPI · SQLite.
**MVP test (the only definition that matters):** *a GM preps and runs a complete real game
session using nothing but this app, and afterwards the app can tell them what happened.*

## 16.1 What is IN the MVP

| Capability | MVP depth |
|---|---|
| Campaigns | multiple, single local user, one rules system + calendar preset per campaign |
| Wiki & knowledge graph | full: articles, @mentions, typed links, backlinks, tags, hierarchy, red-link create, soft delete |
| Search | full: FTS5 global search + ⌘K palette + entity peek |
| Time engine | full core: clock, presets (Harptos/Generic), manual/wait/rest/travel/combat advancement, scheduled events (interval + calendar recurrence), preview + digest |
| Chronicle | full core: domain event log, timeline + filters + manual entries, sessions with live mode + auto-links, quick notes |
| Rules engine | plugin interface + **D&D 5e** + `simpletest` CI stub; generic sheet renderer + bespoke 5e stat block |
| Monsters | SRD pack, facet search, custom + variants |
| Party & PCs | party record, PC sheets, rests via plugin, gold/inventory/reputation |
| NPC tracking | status, current location, location history + "where was X" queries, met-party tracking |
| Quests | types, status lifecycle, giver/rewards/deadline (auto-expire), dependencies (list view) |
| Encounters & combat | builder + difficulty, event-sourced tracker with undo/redo, summary → timeline + clock |
| Live dashboard | full: composite view, panels, presets, embedded tracker |
| Story engine | **flags only** + flag history (the state substrate; graph ships in v1.0) |
| Maps | upload + tiling, viewer, entity-linked markers, notes, child-map drill-down |
| Data safety | WAL, rotating backups, pre-migration backup, soft delete, rebuild-projections CLI |

## 16.2 Milestones (aligned to the [sprint plan](12-roadmap.md); effort = full-time weeks)

| Milestone | Content | Sprints | Effort | Cumulative |
|---|---|---|---|---|
| **M0 Walking skeleton** | pipeline, registry, CI, typed client, shell | 1–2 | 4 w | 1 mo |
| **M1 The Wiki** *(first daily-usable build)* | articles, mentions, links/backlinks, hubs, search, palette | 3–5 | 6 w | 2.5 mo |
| **M2 The Clock & Ledger** | calendar math, advancement loop, scheduled events, timeline, sessions | 6–8 | 6 w | 4 mo |
| **M3 The Engine & Bestiary** | plugin interface, 5e, monsters, party/PCs, rests | 9–11 | 6 w | 5.5 mo |
| **M4 The Table — MVP** | encounters, combat tracker, dashboard, **run a real session** | 12–14 | 6 w | **7 mo** |
| **M5 Atlas & Threads** | maps, quest graph/board, NPC schedules, travel planner | 15–17 | 6 w | 8.5 mo |
| **M6 v1.0** | Nimble, export/import, backups drill, story graph, perf/onboarding/docs | 18–20 | 6 w | **10 mo** |

Part-time reality check: at ~15 h/week these calendar numbers ×2.5. If that horizon is too
long, the pre-agreed **scope release valves** are (in order): maps drop to untiled ≤4k images
(–1.5 w) · story flags UI drops to settings-page table (–1 w) · quest DAG visualization drops
to dependency list (–1 w) · Nimble slips past 1.0 with `simpletest` still guarding the
interface (–2 w, accepts more R-3 exposure).

## 16.3 Sequencing logic (why this order)

M1 before everything user-visible: the wiki is the substrate every other feature writes into,
and it is the daily-use hook that keeps a solo project alive (R-2, R-9). M2 before rules/
combat: the time engine is the highest-risk novel subsystem (R-1) and events/sessions must
exist before anything can be recorded against them. M3 before M4: the combat tracker is
meaningless without stat blocks. Maps in M5, not MVP-critical path: they are navigation
sugar, and the R-6 fallback keeps them cuttable. Nimble in M6 *after* real 5e play: the
second system is a verification instrument, and it verifies more the more reality has
touched the interface.

## 16.4 Deferred past v1.0 (decided now, so cutting is policy rather than defeat)

| Deferred | Why deferring is safe |
|---|---|
| Campaign sharing / multi-GM, hosting, PostgreSQL | schema seams in place (ADR-011, §14.6); zero MVP persona demand |
| Story-engine auto-triggers (FR-4.5) | suggestions flow covers the need with GM consent (R-10) |
| Calendar editor UI | presets + JSON editing cover early adopters; model is final |
| Shop inventory/economy, faction simulation, weather, downtime catalog | `narrate` scheduled events approximate all of them today |
| AI recap & timeline summarization | event log designed as substrate (ADR-012); pure reader modules later |
| Article version history, entity templates, importers, custom fields | additive; `extras_json` and audit events already reserve the space |
| Handout export, desktop packaging (Tauri), tablet polish | distribution/polish, not capability |
| Polygon map regions & layers (if time presses) | markers deliver the core navigation value |

## 16.5 Definition of Done — v1.0

All FR items marked M and S implemented (or on the release-valve list with owner sign-off) ·
NFR-1 numbers measured green in CI on the 50k fixture · restore drill and export/import
round-trip passed · Nimble end-to-end journey green · docs: install, first-campaign, backup/
restore, calendar JSON, plugin-author guide · fresh-machine install to first NPC in under
five minutes, timed.
