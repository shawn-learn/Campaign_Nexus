# 5. Architecture Decision Records

Each ADR: context → decision → justification → consequences. All are **Accepted** for the design
baseline unless marked otherwise.

---

## ADR-001: Modular Monolith (not microservices, not a plain monolith)

**Context.** Options mandated for evaluation: monolith vs modular monolith vs microservices.
The system has ~9 clearly separable subdomains (wiki/graph, time, story, combat, rules, search,
sessions, maps, sharing) but one developer, one deployment target (the GM's machine), and heavy
cross-domain transactions (advancing time touches NPCs, quests, events, timeline atomically).

**Decision.** A **modular monolith**: one FastAPI process, one database, with code organized into
modules that mirror the bounded contexts of the [domain model](04-domain-model.md). Module rules:

- Each module owns its tables, services, and API router.
- Modules expose a small public interface (service functions + Pydantic types); cross-module
  imports of internals are blocked by import-linting in CI.
- Cross-module *reactions* go through the in-process domain event bus (see ADR-004), not direct
  calls, whenever the dependency would otherwise be circular or incidental.

**Why not microservices.** Every microservices benefit is absent here: no independent scaling
needs (one user), no team boundaries (one developer), no independent deployability needs. Every
cost is present: distributed transactions would destroy the atomicity that the time engine
requires (NFR-2.1), and operating N services on a GM's laptop is absurd.

**Why not an unstructured monolith.** The subsystems are genuinely complex and long-lived
(NFR-4.1). Without enforced boundaries, the rules engine leaks into the combat tracker, game
system assumptions leak into core, and extensibility goal G6 dies. The modular monolith buys
microservice-style boundaries at monolith-style cost.

**Consequences.** ➕ Single-transaction cross-domain operations; trivial deployment; refactoring
across boundaries is cheap. ➖ Discipline is enforced by lint + review, not process isolation.
If hosted multi-tenant deployment ever demands extraction, module boundaries are the seams.

---

## ADR-002: SQLite as the system of record (PostgreSQL-portable schema)

**Context.** Mandated evaluation: SQLite; graph database integration. Data volume per campaign is
modest (NFR-1.6); deployment is local-first single-writer.

**Decision.** **SQLite** with WAL mode, foreign keys ON, FTS5 for search, JSON1 for
rules-system documents. Accessed via SQLAlchemy 2.0; migrations via Alembic. Schema written in
the portable SQL subset; SQLite-specific features isolated behind repository interfaces (NFR-5.2).

**Justification.**
- Local-first, zero-administration, single file = trivially backup-able (copy the file) —
  directly serves NFR-2 (data safety) and NFR-5.1 (one-command deployment).
- Single-writer workload is SQLite's sweet spot; WAL gives readers-don't-block-writers, which
  covers the dashboard-polls-while-GM-edits pattern.
- FTS5 satisfies NFR-1.2 (sub-100 ms search) without an external search service.
- 1M events / 500k rows of links is far below SQLite's practical limits.

**Consequences.** ➕ Simplicity, durability, portability. ➖ Hosted multi-tenant deployment
later requires the planned PostgreSQL port (bounded by NFR-5.2); no concurrent multi-process
writes (irrelevant for MVP; revisit with shared campaigns — see ADR-011).

---

## ADR-003: Knowledge graph in relational tables — no graph database

**Context.** The knowledge graph (G2) suggests Neo4j or similar. Mandated evaluation: graph
database integration.

**Decision.** Model the graph as an **`entity` registry table + typed `link` edge table** in
SQLite. Traversals use recursive CTEs. No graph database.

**Justification.**
- Actual query shapes are shallow: backlinks (1 hop), neighborhood view (1–2 hops), location
  containment chains (recursive but tiny). No shortest-path, no centrality, no deep pattern
  matching — nothing that rewards a graph engine.
- A second datastore breaks the single-transaction guarantee (an edge insert and the article
  save must commit together), doubles backup complexity, and violates one-command deployment.
- Bidirectionality (FR-2.3) is a *storage-once, query-both-directions* property: an edge
  `(A)-[mentions]->(B)` answers both "A's links" and "B's backlinks" with two indexed lookups.

**Consequences.** ➕ One store, one transaction, one backup. ➖ If a future feature genuinely
needs graph analytics (e.g., "influence maps"), export the edge table to an in-memory graph
(networkx) at query time — the data model already is a property graph.

---

## ADR-004: Hybrid event log — not pure event sourcing

**Context.** Mandated evaluation: event sourcing. The domain screams "history matters":
timeline auto-generation (FR-8.1), NPC location history (FR-6.2), party history (FR-7.2),
combat undo (FR-12.4), future AI recaps. But pure event sourcing (state = fold(events)) carries
heavy costs: eventual-consistency projections, schema evolution of events, rebuild tooling,
and a much harder mental model — bad trade-offs for a solo maintainer.

**Decision.** A **hybrid**: current state lives in normal relational tables (the write model
*is* the read model for entities), **and** every state-changing operation appends one or more
immutable **domain events** to an `domain_event` log **in the same transaction**. Projections
(timeline entries, NPC location history, session auto-links) are updated synchronously in that
transaction too — cheap because they are inserts.

Pure event sourcing is used in exactly one place: **inside an active combat encounter**
(ADR-005), where undo/redo makes it pay for itself.

Rules:
1. No mutation without a domain event ("if it isn't in the log, it didn't happen").
2. Events are facts, past tense, campaign-time-stamped and real-time-stamped
   (`npc_relocated`, `quest_completed`, `time_advanced`).
3. Events are append-only; corrections are compensating events (NFR-2.3).
4. The in-process event bus dispatches committed events to module subscribers (story-engine
   trigger evaluation, dashboard cache invalidation).

**Why not full CQRS with async projections.** With one user and SQLite, synchronous projection
updates cost microseconds and buy read-your-writes consistency everywhere (FR-14.3). We keep the
CQRS *idea* — purpose-built read models like the timeline and the dashboard aggregate — without
the eventual-consistency machinery. This is "lightweight CQRS": separate read models, same
store, same transaction.

**Consequences.** ➕ Complete history, simple queries for current state, undo where it matters,
AI-ready event stream, no rebuild infrastructure. ➖ Dual-write discipline is required —
enforced by routing all mutations through command handlers that both mutate state and emit
events (see [Event-Sourcing Design](06-event-sourcing.md)); direct table writes outside command
handlers are forbidden by convention and code review.

---

## ADR-005: Combat tracker as an event-sourced state machine

**Context.** FR-12.4 requires unlimited undo/redo; combat is high-frequency mutation.

**Decision.** An active combat is a sequence of **combat actions** (apply damage, next turn, add
condition…) stored per-encounter-run. Current combat state is a fold of actions; undo = decrement
fold pointer, redo = increment; new action after undo truncates the redo tail. On combat end, the
run is summarized into ordinary domain events (participants, rounds, outcomes, casualties) and
the campaign clock advances by rounds × round-length (FR-12.5). The action log is retained for
history but the campaign-level projections consume only the summary events.

**Justification.** Undo/redo falls out of the design for free; combat state is small (fold cost
is trivial); keeping fine-grained combat actions out of the campaign event log preserves the
timeline's signal-to-noise ratio.

---

## ADR-006: REST API, not GraphQL

**Context.** Mandated evaluation: GraphQL vs REST. The graph-shaped domain superficially favors
GraphQL.

**Decision.** **REST** (FastAPI + Pydantic → OpenAPI → generated TypeScript client), with two
pragmatic additions: (a) **composite read endpoints** for aggregate screens (dashboard, entity
page with links/backlinks) so the UI isn't chatty; (b) an `include=` expansion parameter on
entity reads for common relation embedding.

**Justification.**
- Exactly one API consumer, which we control: GraphQL's marquee benefit (arbitrary client-driven
  queries) has no customer.
- FastAPI's native path is REST: request validation, OpenAPI generation, and typed client
  generation (`openapi-typescript`) give end-to-end type safety (NFR-4.3) with zero extra
  infrastructure. GraphQL would add a schema layer, resolver layer, N+1 management (dataloaders),
  and its own caching story — pure cost here.
- Composite endpoints answer the real concern (screen-shaped reads) with a fraction of the
  machinery, and they're the natural place to enforce NFR-1.1.

**Consequences.** ➕ Less machinery, typed client for free. ➖ New aggregate screens may need new
composite endpoints — acceptable; they're thin orchestrations of module services. Revisit only if
a third-party API is ever productized.

---

## ADR-007: React + TypeScript SPA; TanStack Query/Router; Zustand

**Context.** Stack mandated (React + TypeScript). Decisions remaining: build tooling, data
layer, routing, state.

**Decision.** Vite + React 18 + TypeScript (strict). **TanStack Query** for all server state
(caching, invalidation, optimistic updates); **TanStack Router** for type-safe routes;
**Zustand** for the small set of true client state (combat-tracker UI, dashboard layout, command
palette); **Tiptap** (ProseMirror) for the article editor with a custom `@mention` node that
produces entity links.

**Justification.** Server-cache-first architecture matches the app: almost all state is server
state, and Query's invalidate-on-mutate model implements FR-14.3 (dashboard freshness) cleanly.
Tiptap is chosen because mentions-as-first-class-nodes (not plain text) make link extraction
lossless — the backbone of FR-2.2/2.3. No SSR/Next.js: there is no SEO or first-paint-on-slow-
network requirement for a local tool; a SPA served statically by FastAPI is simpler.

---

## ADR-008: Leaflet (CRS.Simple) for maps, not MapLibre

**Context.** Mandated evaluation: Leaflet vs MapLibre.

**Decision.** **Leaflet** with `CRS.Simple` (pixel coordinates) over tiled raster images;
`react-leaflet` bindings. Large uploads are tiled server-side into a deep-zoom pyramid.

**Justification.** MapLibre's strengths — vector tiles, styled cartography, WebGL rendering of
geographic data — don't apply: fantasy maps are hand-drawn **raster images** with no geographic
projection. Leaflet's raster/`CRS.Simple` path is the canonical solution, its marker/popup/layer
model maps 1:1 onto FR-3, and its plugin ecosystem (draw tools for polygon regions, FR-3.5) is
mature. Leaflet is also markedly simpler — the right cost profile for a nav-oriented (not
render-oriented) map feature.

**Consequences.** ➖ If post-1.0 features demand thousands of live markers or vector styling,
revisit; until then Leaflet with marker clustering is comfortably sufficient.

---

## ADR-009: React Flow for story and quest graphs

**Context.** Mandated evaluation. FR-4.6 (story graph editor), FR-10.4 (quest dependency view).

**Decision.** **React Flow** for both, with `dagre` auto-layout for the read-only quest
dependency view and manual layout (persisted node positions) for the story graph editor.

**Justification.** React Flow is the de-facto React library for node-graph editing: custom node
rendering (status-colored quest cards), edge labels (conditions), pan/zoom, and controlled state
that round-trips cleanly to our graph tables. Building on raw SVG/canvas would be weeks of
undifferentiated work.

---

## ADR-010: Rules engine as backend plugins + JSON-schema documents

**Context.** G6 / FR-11: multiple RPG systems, no hardcoding, no schema redesign per system.

**Decision.** Each rules system is a **Python plugin package** implementing a `RuleSystem`
interface (stat-block JSON Schemas per sheet type, derived-stat computation, conditions,
rest/travel/initiative/difficulty logic, content packs). All system-specific data is stored in
**JSON documents** in generic tables, validated against the plugin's schemas. The frontend
renders stat blocks from schema + layout hints, with an escape hatch for system-specific
React components shipped in-app per system. Full design: [Rules Engine](08-rules-engine.md).

**Justification.** The only architecture that satisfies "additional systems without database
redesign" (FR-11.6). JSON1 + generated columns give us queryable facets (CR, level) without
per-system tables.

---

## ADR-011: Local-first single-user MVP; sharing designed-in, deferred

**Context.** FR-1.5 (shared campaigns) vs one-developer MVP reality.

**Decision.** MVP runs locally, binds to localhost, single default user — but the schema carries
`user`, `campaign_member(role)`, and `created_by` attribution from day one, and every query is
campaign-scoped (NFR-6.2). Multi-GM sharing ships post-1.0 with a hosted or self-hosted
deployment story and likely the PostgreSQL port (ADR-002).

**Justification.** Sharing is a persona-P4 need and the single costliest feature family
(accounts, hosting, sync/conflicts). Deferring it keeps MVP achievable; designing it into the
schema now keeps deferral cheap (persona rule 4).

---

## ADR-012: AI features deferred; event log is the enabling substrate

**Context.** AI roadmap (recap generation, timeline summarization) — include now or later?

**Decision.** **Excluded from MVP.** No compelling architectural reason to build them now,
*because* the architecture already produces what they need: ADR-004's campaign-time-stamped,
session-scoped, entity-linked event log is precisely the input an LLM recap/summarizer wants.
The only MVP obligation is discipline: keep events descriptive (structured payload + generated
human-readable text), which we want for the timeline anyway. See
[Future Enhancements](15-future-enhancements.md).

---

## Decision summary

| Topic | Decision |
|---|---|
| Architecture style | Modular monolith, in-process event bus |
| Persistence | SQLite (WAL, FTS5, JSON1), SQLAlchemy 2.0, Alembic; PG-portable |
| Knowledge graph | Relational edge table + recursive CTEs; no graph DB |
| Event sourcing | Hybrid: state tables + append-only domain event log, same transaction |
| CQRS | Lightweight: synchronous purpose-built read models, single store |
| Combat | Fully event-sourced per encounter-run (undo/redo), summarized into domain events |
| API | REST + composite endpoints; OpenAPI → generated TS client |
| Frontend | Vite, React 18, TS strict, TanStack Query/Router, Zustand, Tiptap |
| Maps | Leaflet `CRS.Simple`, server-side tiling |
| Node graphs | React Flow (+dagre) |
| Rules systems | Python plugin interface + JSON-schema documents |
| Sharing | Schema-ready now, feature post-1.0 |
| AI | Post-MVP; event log designed as its substrate |
