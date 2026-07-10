# 3. Functional Requirements

Requirements use MoSCoW priority (M = Must for MVP, S = Should for v1.0, C = Could post-1.0).
IDs are stable and referenced from the roadmap, test strategy, and risk register.

## FR-1 Campaign Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1.1 | Create, edit, archive, delete campaigns; multiple campaigns per user | M |
| FR-1.2 | Each campaign owns its entities: worlds, regions, countries, cities, dungeons, buildings, maps, NPCs, factions, quests, encounters, monsters, session logs, timeline, party | M |
| FR-1.3 | Campaign selects exactly one rules system at creation (5e, Nimble, …) | M |
| FR-1.4 | Campaign selects a calendar definition (default or custom) at creation | M |
| FR-1.5 | Campaigns are private by default; owner may share with other GMs with a role (viewer/editor) | C |
| FR-1.6 | Full campaign export/import (single-file archive: entities, events, media) | S |

## FR-2 Knowledge Graph & Articles

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1 | Every entity has an article page: rich text, structured fields, image, tags | M |
| FR-2.2 | Rich text supports `@mention` of any entity, creating a typed link on save | M |
| FR-2.3 | All links are bidirectional: target entity automatically lists backlinks ("Referenced by") | M |
| FR-2.4 | Explicit typed relationships (e.g., NPC —member_of→ Faction, Location —within→ Region) with optional notes and time validity | M |
| FR-2.5 | Location hierarchy: World ⊃ Region ⊃ Country ⊃ City ⊃ District/Building/Dungeon, arbitrary depth | M |
| FR-2.6 | Deleting an entity shows all inbound references and requires explicit handling (relink or break) | M |
| FR-2.7 | Relationship graph visualization around any entity (n-hop neighborhood) | S |
| FR-2.8 | Entity templates (e.g., "Tavern" pre-fills fields) | S |

## FR-3 Interactive Maps

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-3.1 | Upload a raster image as a map; pan/zoom (deep-zoom tiling for large images) | M |
| FR-3.2 | Map types: world, region, city, dungeon, building — a map is attached to a location entity | M |
| FR-3.3 | Place markers on maps; each marker links to an entity (NPC, location, quest, encounter, event, note) | M |
| FR-3.4 | Markers to child maps (click city on world map → open city map) with breadcrumb back-navigation | M |
| FR-3.5 | Clickable polygon regions with entity links | S |
| FR-3.6 | Marker layers/filtering by entity type and tag | S |
| FR-3.7 | Free-floating map notes (pins without entity) | M |
| FR-3.8 | No player-facing features (fog of war, tokens, visibility) — permanently out of scope | — |

## FR-4 Branching Story Engine

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-4.1 | Campaign state store: named flags/variables per campaign (e.g., `merchant_alive = true`) | M |
| FR-4.2 | Story nodes (potential events/scenes) arranged in a directed graph with branch and merge | S |
| FR-4.3 | Edges carry conditions (predicates over campaign state) and node entry runs consequences (set flag, activate quest, schedule event, move NPC) | S |
| FR-4.4 | Node status lifecycle: possible → active → resolved/abandoned; manual resolution by GM in MVP | S |
| FR-4.5 | Automatic trigger evaluation on domain events / time advancement | C |
| FR-4.6 | Graph editor (React Flow): visualize and edit the story graph | S |

## FR-5 Campaign Time Engine

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-5.1 | Campaign clock: current date + time-of-day on a configurable calendar; derived: days elapsed, week/month/year, season | M |
| FR-5.2 | Advance time by: manual adjustment, short rest, long rest, travel, downtime, waiting, combat rounds | M |
| FR-5.3 | Travel time computed from distance, terrain, pace, mount/vehicle/special method (tables supplied by rules plugin) | M |
| FR-5.4 | Rest advancement applies system rest rules (HP, spell slots, resources) to party/NPC status via rules plugin | S |
| FR-5.5 | Scheduled events: one-shot and recurring (festival, NPC itinerary step, quest deadline, shop restock); firing when clock passes their time | M |
| FR-5.6 | Time advancement is transactional: clock moves, due events fire, consequences apply, domain events are logged — atomically | M |
| FR-5.7 | Every domain event stores the campaign-time at which it occurred | M |
| FR-5.8 | Custom calendar editor UI (month names/lengths, weekdays, leap rules, moons) | C (data model M) |

## FR-6 NPC Tracking

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-6.1 | NPC record: current location, status (alive/dead/missing/…), faction memberships, goals, secrets, inventory, relationships | M |
| FR-6.2 | Location history: every NPC relocation is an event; "where was X at campaign time T / during session N" is queryable | M |
| FR-6.3 | Knowledge tracking: NPC knows-about links to entities/secrets ("which NPCs know about the artifact?") | S |
| FR-6.4 | Party interaction tracking: has-met flag, last-interaction time, per-session interaction list | M |
| FR-6.5 | NPC schedules: recurring itineraries (daily/weekly) and planned journeys that relocate the NPC as time advances | S |
| FR-6.6 | Saved queries: NPCs by status, location, faction, met-party, knows-X | M |

## FR-7 Party Tracking

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-7.1 | Party record per campaign: members (PCs), current location, gold, shared inventory, reputation per faction | M |
| FR-7.2 | Travel history and rest history as projections of the event log | M |
| FR-7.3 | Active/completed quest lists | M |
| FR-7.4 | PC records with rules-system character sheet (see FR-11) | M |

## FR-8 Timeline

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-8.1 | Every significant domain event auto-generates a timeline entry (arrivals, rests, quest changes, combat, deaths, discoveries, world events) | M |
| FR-8.2 | Manual timeline entries (backstory/historical lore with campaign dates, including pre-campaign history) | M |
| FR-8.3 | Filter timeline by session, NPC, quest, location, faction, date range, event type | M |
| FR-8.4 | Timeline entries deep-link to their entities and session | M |

## FR-9 Session Logs

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-9.1 | Session record: real date, campaign day(s) covered, summary, decisions, discoveries, loot, XP, notes | M |
| FR-9.2 | Live session mode: start/end session; all events logged during the session are attached to it | M |
| FR-9.3 | Auto-linked entities: NPCs interacted with, locations visited, quests touched, encounters run — derived from the session's events | M |
| FR-9.4 | Quick-capture note field always available during live play | M |

## FR-10 Quests

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-10.1 | Quest types (main/side/hidden), status lifecycle (unknown → available → active → completed/failed/expired) | M |
| FR-10.2 | Quest fields: giver (NPC), locations, rewards, deadline (campaign time), completion conditions, dependencies on other quests | M |
| FR-10.3 | Deadline expiry via scheduled event (quest auto-expires when clock passes deadline) | S |
| FR-10.4 | Dependency-graph visualization (React Flow) | S |

## FR-11 Rules Engine, Monsters, Characters

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-11.1 | Rules system plugin interface: stat-block schema, derived stats, conditions list, rest rules, travel paces, initiative rules, encounter-difficulty calc | M |
| FR-11.2 | D&D 5e plugin (SRD content) | M |
| FR-11.3 | Nimble plugin | S (interface proven in MVP by a stub second system) |
| FR-11.4 | Monster database: built-in (from plugin content packs) + custom + variants ("copy & modify") ; searchable/filterable by system-defined facets (CR, type, …) | M |
| FR-11.5 | Stat blocks for PCs, NPCs, monsters rendered from the active system's schema | M |
| FR-11.6 | No system-specific fields in core tables; all system data lives in schema-validated JSON documents | M |

## FR-12 Encounters & Combat

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-12.1 | Encounter builder: monsters (with counts), NPCs, terrain, environmental effects, hazards, notes; difficulty estimate from rules plugin | M |
| FR-12.2 | Encounters are reusable and linkable to locations, quests, maps | M |
| FR-12.3 | Combat tracker: initiative order, HP, temp HP, conditions, status effects, concentration, legendary/lair actions, round counter | M |
| FR-12.4 | Unlimited undo/redo within a combat (command/event-sourced combat state) | M |
| FR-12.5 | Ending combat writes summary events (participants, casualties, rounds, duration) to the campaign event log → timeline; combat rounds advance the campaign clock | M |

## FR-13 Search

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-13.1 | Global full-text search across all entity types, session logs, and timeline entries; ranked results with type badges | M |
| FR-13.2 | Search-as-you-type (< 100 ms for prefix queries), keyboard-driven (⌘K palette) | M |
| FR-13.3 | Tags on all entities; filter search by type and tag | M |

## FR-14 Live Session Dashboard

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-14.1 | Single screen showing: campaign date/time (+ advance controls), party location, active quests, NPCs at current location, encounters at/near current location, current map, initiative tracker, pinned stat blocks, quick notes, recent events feed, global search | M |
| FR-14.2 | Dashboard panels deep-link to full entity pages (open in side-panel to avoid losing dashboard context) | M |
| FR-14.3 | Dashboard reflects state changes immediately (advancing time refreshes NPC lists, etc.) | M |

---

# 4. Non-Functional Requirements

## NFR-1 Performance

| ID | Requirement |
|----|-------------|
| NFR-1.1 | Entity page load (article + links + backlinks): < 200 ms server time, < 1 s perceived |
| NFR-1.2 | Global search results: < 100 ms for prefix queries on 50k entities (SQLite FTS5) |
| NFR-1.3 | Combat tracker interactions (damage, next turn, undo): < 50 ms perceived — optimistic UI |
| NFR-1.4 | Time advancement including firing 100 scheduled events: < 1 s |
| NFR-1.5 | Map pan/zoom at 60 fps for images up to 16k×16k (tiled) |
| NFR-1.6 | Targets hold at: 50k entities, 500k links, 1M domain events per campaign |

## NFR-2 Reliability & Data Safety

| ID | Requirement |
|----|-------------|
| NFR-2.1 | The campaign is irreplaceable creative work: **zero tolerance for data loss.** All multi-step mutations are single ACID transactions |
| NFR-2.2 | Automatic timed backups of the SQLite file (rotating, before every schema migration, and on session start) |
| NFR-2.3 | Domain event log is append-only; corrections are compensating events, never destructive edits |
| NFR-2.4 | Soft-delete for entities (recoverable); hard delete only via explicit purge |
| NFR-2.5 | One-click full export to an open format (JSON + media archive) — data outlives the app |

## NFR-3 Usability

| ID | Requirement |
|----|-------------|
| NFR-3.1 | Two-click rule: any entity reachable from any screen within two interactions (search counts as one) |
| NFR-3.2 | Keyboard-first affordances: command palette, search, combat tracker hotkeys |
| NFR-3.3 | Works on a 13″ laptop and an iPad-sized tablet (live-play form factors); desktop-optimized |
| NFR-3.4 | Dark mode (live play happens in dim rooms) |
| NFR-3.5 | A new campaign is usable in < 5 minutes: create campaign → add party → add first location → start session |

## NFR-4 Maintainability & Extensibility

| ID | Requirement |
|----|-------------|
| NFR-4.1 | Modular monolith with enforced module boundaries (import-linted); modules communicate via interfaces and domain events |
| NFR-4.2 | New rules system: zero core-schema changes; new entity type: additive migration only |
| NFR-4.3 | Type safety end-to-end: Pydantic models → OpenAPI → generated TypeScript client |
| NFR-4.4 | Schema migrations via Alembic; every migration reversible or explicitly documented as not |
| NFR-4.5 | Code health gates: ruff + mypy (strict) on backend, eslint + tsc (strict) on frontend, CI on every commit |

## NFR-5 Portability & Deployment

| ID | Requirement |
|----|-------------|
| NFR-5.1 | MVP deployment: single process (FastAPI serves API + built frontend) + one SQLite file + media folder; runs on the GM's own machine with one command |
| NFR-5.2 | SQL restricted to the SQLAlchemy-portable subset where practical; SQLite-specific features (FTS5, JSON1) isolated behind repository interfaces so a future PostgreSQL port is a bounded task |
| NFR-5.3 | No cloud dependency for core functionality; fully offline-capable |

## NFR-6 Security & Privacy

| ID | Requirement |
|----|-------------|
| NFR-6.1 | Local-first MVP binds to localhost by default; auth layer present but in single-user mode |
| NFR-6.2 | All authorization is campaign-scoped from day one (no "global" entity access paths) |
| NFR-6.3 | Media uploads validated (type, size); no execution of uploaded content |
| NFR-6.4 | See [Security Model](11-security-model.md) for the full model |
