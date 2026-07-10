# 13. API Design

REST per ADR-006. FastAPI + Pydantic v2; OpenAPI 3.1 spec is generated and is the contract —
the TypeScript client is generated from it in CI (drift = build failure).

## 13.1 Conventions

- Base: `/api/v1`. All campaign data under `/api/v1/campaigns/{campaign_id}/…` — the path
  itself carries the authorization scope (NFR-6.2).
- JSON bodies; `snake_case`; UUIDs as strings; campaign time as integer minutes; real time
  ISO-8601 UTC.
- Errors: RFC 9457 problem+json (`type`, `title`, `status`, `detail`, `errors[]` for field
  validation). Domain violations use stable `type` slugs (`…/errors/location-cycle`).
- Pagination: cursor-based (`?cursor=&limit=`) on all list endpoints; filters are query params.
- Concurrency: entities carry `version` (integer); writes send `If-Match`-style
  `expected_version` → `409 Conflict` on mismatch (protects the article editor; matters more
  with sharing later).
- Idempotency: mutating commands accept an optional `Idempotency-Key` header (safe retries).

## 13.2 Resource surface (summary)

### Wiki / graph
```
GET/POST      /entities                         ?type=&tag=&q=  (list/create; polymorphic
                                                 body: registry fields + typed `data` object)
GET/PATCH/DELETE /entities/{id}                 ?include=links,backlinks,tags,history
POST          /entities/{id}/restore
GET           /entities/{id}/neighborhood       ?depth=1..2   (graph view payload)
GET/POST/DELETE /entities/{id}/links            (typed relations; mention links are read-only)
GET           /entities/{id}/references         inbound refs incl. markers, quests (delete preflight)
GET/POST      /tags ; PUT/DELETE /tags/{id}
```

### Maps
```
POST          /maps                              (multipart: image + metadata) → 202 tiling job
GET           /maps/{id}/tiles/{z}/{x}/{y}.webp  (static-served pyramid)
GET/POST/PATCH/DELETE /maps/{id}/markers, /maps/{id}/regions
```

### Time
```
GET           /clock                             current time + formatted calendar breakdown
POST          /clock/advance                     {mode: manual|rest_short|rest_long|wait|downtime,
                                                  target|duration, note} → AdvanceReport
POST          /travel/plan                       legs[] → preview {duration, arrival, would_fire[]}
POST          /travel/commit                     plan → AdvanceReport
GET/POST/PATCH/DELETE /scheduled-events          ?status=&until=
GET/POST/PATCH/DELETE /npcs/{id}/schedules
```
`AdvanceReport` = `{from, to, fired: [{event, narrative}], clock: {...formatted}}` — the UI
renders it as the "what just happened" toast/digest.

### Chronicle
```
GET           /events                            ?type=&entity=&session=&from_game=&to_game=&cursor=
GET           /timeline                          ?filters…   (curated projection)
POST          /timeline/manual                   lore entries
PATCH         /timeline/{id}                     {is_hidden, significance, title}
GET/POST      /sessions ; PATCH /sessions/{id}
POST          /sessions/{id}/start | /end        (≤1 live enforced)
POST          /notes                             quick capture → note_captured event
```

### Playbook
```
GET/PATCH     /party                             (+ /party/members)
POST          /party/move                        {to_location, method} (no travel-time: teleports/retcons)
GET/POST/PATCH /quests… ; POST /quests/{id}/status {to, note}
GET           /quests/graph                      DAG payload for React Flow
GET/POST/PATCH/DELETE /encounters…
POST          /combat-runs                       {encounter_id?} → initial state
GET           /combat-runs/{id}                  state at cursor (+ actions tail)
POST          /combat-runs/{id}/actions          {action_type, payload, client_seq} → new state hash
POST          /combat-runs/{id}/undo | /redo     → state
POST          /combat-runs/{id}/end              → summary events, clock advance
```

### Rules & monsters
```
GET           /rule-systems                      installed plugins + facet manifests
GET           /rule-systems/{id}/schema/{sheet_type}
GET           /rule-systems/{id}/layout/{sheet_type}
GET           /monsters                          ?q=&facet1_num_gte=… (facet filtering)
POST          /monsters/{id}/variant             copy-on-write clone
GET/PUT       /stat-blocks/{id}                  (PUT validates against plugin schema)
POST          /stat-blocks/validate              dry-run validation for the sheet editor
```

### Story engine
```
GET/PUT       /flags ; GET /flags/history/{key}
GET/POST/PATCH/DELETE /story/nodes, /story/edges
GET           /story/suggestions                 nodes whose conditions evaluate true now
POST          /story/nodes/{id}/activate|resolve|abandon
POST          /story/conditions/validate         DSL parse/typecheck for the editor
```

### Search & composite reads
```
GET           /search                            ?q=&types=&tags=&limit=   (FTS, ranked, <100ms)
GET           /views/dashboard                   one-call payload for the live dashboard
GET           /views/entity/{slug}               entity + typed data + links + backlinks + tags
                                                 + history-slice + type-widgets (one-call page)
```
Composite `views/*` endpoints exist for the two hottest screens (ADR-006); everything else
composes standard resources with `include=`.

### System
```
GET           /export                            full campaign archive (JSON + media zip)
POST          /import
GET           /healthz ; GET /version
```

## 13.3 Command semantics

State-changing endpoints are **commands** (§8.1): they run the full pipeline and respond with
`{result, events: [{type, narrative}]}` so the UI can toast what happened and invalidate the
right Query caches (event types map to cache keys in one table in `api/`).

## 13.4 Realtime

MVP: none needed — single user; mutations return their own consequences, and TanStack Query
invalidation covers freshness (FR-14.3). Post-MVP (shared campaigns): add
`GET /campaigns/{id}/events/stream` (SSE, last-event-id resume) broadcasting committed domain
events; the invalidation table then doubles as the SSE handler. SSE over WebSocket: one-way
notify is all that's required, and SSE survives proxies and reconnects trivially.

## 13.5 Performance notes

- `views/dashboard` is assembled in one request: ~8 indexed queries in one read transaction —
  well under the NFR-1.1 budget on SQLite.
- Tile and media endpoints are cache-friendly (`immutable`, content-addressed names).
- N+1 discipline: list endpoints join their display fields; `include=` expansions are batched
  (`WHERE … IN`), never per-row.
