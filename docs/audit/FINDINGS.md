# Campaign Nexus — Audit Findings Log

Shared log for the audit defined in [AUDIT_PLAN.md](AUDIT_PLAN.md). Every step appends
here. Executive summary is written by step 14.

## Severity taxonomy

- **P0** — correctness bug or data-loss risk
- **P1** — supportability risk (can't debug/onboard/operate it)
- **P2** — convention or docs drift, maintainability debt
- **P3** — polish / nice-to-have

**Status values:** `open` · `accepted` (consciously wontfix, with reason) · `fixed` · `merged into AUD-NNN`

## Entry template

```
### AUD-NNN · P? · short title
- **Step:** N — step name
- **Where:** file/path or area
- **What:** description of the issue
- **Suggested fix:** …
- **Status:** open
```

---

## Step 0 baseline — 2026-07-18

All checks run locally on Windows (backend venv: Python 3.14.0, tool versions match
`uv.lock`).

**Initial run** (before fixes). Backend tools had to be invoked as
`uv run python -m <tool>` because the venv's `.exe` launchers were broken (AUD-005):

| Check | Result | Time | Notes |
|---|---|---|---|
| ruff | **FAIL — 89 errors** | 0.1s | 86 autofixable: 72 UP045, 12 I001, 2 RUF001, 1 UP035, 1 RUF100, 1 F841 |
| mypy strict | **FAIL — 9 errors / 7 files** | 6.5s | Included two real bugs in `merchant/service.py` |
| lint-imports | **FAIL — 1 of 3 contracts** | 0.5s | `playbook.travel → atlas.models` |
| pytest | **PASS — 410 tests** | 52s | Only passed when run via `python -m pytest` |
| openapi.json fresh | PASS | 2s | |
| eslint | **FAIL — 1 error, 2 warnings** | 2.4s | Unused `_childMapName` |
| tsc typecheck | PASS | 4.7s | |
| vitest | PASS — 73 tests | 3.7s | |
| gen:api client fresh | PASS | 5s | |
| vite build | PASS | 8.5s | 1.29 MB single JS chunk warning (AUD-009) |
| GitHub CI | **RED — last 5 runs failed** | ~20s each | Failed at ruff + eslint, incl. two pushes to `main` |

**After the first fix batch** — every check green, and the plain `uv run <tool>`
invocation works again:

| Check | Result | Time |
|---|---|---|
| ruff | PASS — all checks passed | 0.2s |
| mypy strict | PASS — 127 files | 6.5s |
| lint-imports | PASS — 3 kept, 0 broken | 0.5s |
| pytest | PASS — 410 tests | 52s |
| openapi.json fresh | PASS | 2s |
| eslint | PASS — 0 errors (2 react-refresh warnings) | 2.4s |
| tsc typecheck | PASS | 4.7s |
| vitest | PASS — 73 tests | 3.7s |
| gen:api client fresh | PASS | 5s |
| vite build | PASS | 8.5s |

Runtime verification after the batch: backend boots (migrations + seeding + bootstrap),
`/healthz` returns ok, `/api/v1/equipment-library` serves seeded content (proving the
restructured projector side-effect import in `main.py` still registers), frontend loads
the real Curse of Strahd campaign, and the Merchants page lists all 12 shops in correct
alphabetical order with shop detail + 90 stock lines rendering and no console errors.

CI workflow vs DEVELOPMENT.md: CI runs everything the doc promises. ✔ No gap.

`backend/scripts/` inventory (15): repeatable tools — `export_openapi`,
`rebuild_projections`, `restore_backup`, `import_5etools`; one-off content seeds —
`seed_cos_encounters/images/magic_items/npc_locations/npcs/random_tables/shop`,
`seed_into_the_mists`, `split_appendix_c_treasures`; one-off repairs — `fix_encoding`,
`relink_encounter_combatants`. Per-script verdicts are step 6's job.

---

## Step 1 — Architecture & module boundaries (2026-07-18)

**Checked and clean:**
- `core/pipeline.py` transaction boundary is correct: state mutation → flush → append
  events → flush → run projectors → single `commit()`, with `rollback()` on any
  exception. Projections cannot disagree with the events they derive from.
- Event bus publishes **post-commit only**, isolates each subscriber in try/except, and
  logs failures. It has no subscribers today — documented as a deliberate extension
  seam, not dead code.
- Projector/reset pairing is complete: all three owning modules (chronicle, equipment,
  npcs) register both, and `db_metadata.py` imports all three, so
  `scripts/rebuild_projections.py` replays the full set. No silent gap in rebuild.
- Core primitives are used consistently — no module mints its own ids or reads the
  clock directly (sole exception: `backup/service.py` uses `datetime.now(UTC)` for a
  filename stamp instead of `core/clock.py`; cosmetic, not logged).
- ADR-004's claim that pure event sourcing is used "in exactly one place — inside an
  active combat encounter" holds (`playbook/combat_reducer.py`).
- `seq` allocation is `MAX(seq)+1`, safe only under the single-writer assumption; the
  `uq_event_campaign_seq` unique constraint means a concurrent race fails loudly with
  an IntegrityError rather than corrupting the log. Acceptable for the local-first
  posture — should be revisited if the P-LAN posture in docs/11 is ever pursued.

---

## Step 2 — Data layer (2026-07-18)

Run against a throwaway DB in the scratchpad; the production `campaign_nexus.db` was
only ever opened read-only (`mode=ro`).

**Checked and clean:**
- **Migration chain is linear** — one head (`a9b8c7d6e5f4`), zero branch points/merges,
  and `alembic upgrade head` on an empty DB succeeds end to end.
- **No model↔migration drift.** `revision --autogenerate` against the freshly-migrated
  DB produced an empty `upgrade()` body. (Scratch revision deleted; `alembic/versions/`
  is clean.) This is already automated —
  `tests/test_migrations.py::test_head_schema_matches_the_orm_models` runs the same
  check in CI, which is why there is no drift.
- **A fresh install matches production.** Full `sqlite_master` diff of a
  migrated-from-scratch DB vs the live one: 115 objects each, none missing on either
  side, and the single textual difference is clause *ordering* inside `party`
  (`UNIQUE` before vs after the FK) — semantically identical. The migration chain
  faithfully reproduces the real schema.
- **Pragmas are correct and universal.** `journal_mode=WAL`, `foreign_keys=ON`,
  `busy_timeout=5000`, installed via a `connect` event listener so they apply to every
  pooled connection, and guarded by an `is_sqlite` check. Alembic's env deliberately
  omits them and uses `render_as_batch` for SQLite-safe ALTERs.
- **No SQL injection surface.** Zero f-string/format-built SQL in the whole backend;
  all 33 raw `text()` sites use bound parameters. FTS user input goes through
  `_match_query`, which splits on non-word characters and quotes each token, defusing
  FTS5 operators.
- **JSON columns are validated at the API boundary.** Despite 23 `_json` columns and
  only one `jsonschema` use, the Pydantic request schemas are strongly typed
  (`polygon: list[tuple[float, float]]` with `min_length=3`, `list[CombatantSpec]`,
  `list[TableRow]`); the one loose case (`consequences: list[dict[str, Any]]`) has a
  hand-written closed-catalog `validate()`. Residual risk is limited to writes that
  bypass the API (seed scripts, restored data) — noted, not logged.
- **Media files are not leaking.** 97 `media` rows, 97 referenced, **0 orphaned rows**,
  0 rows with a missing file, 131 files / 58.5 MB on disk. Exactly one stray file (a
  73-byte PNG, almost certainly a test-upload artifact). Not deleting content-addressed
  files on detach is a deliberate, commented choice (shared + backup-covered).
- **Backups rotate.** `prune_backups()` runs after every create, honouring
  `settings.backup_keep` — no unbounded growth.

*For step 11's runbook:* `backup/service.py:169` restores media with
`rmtree(media_dest)` then `copytree` — a restore therefore **destroys any media added
since that backup**. Correct for a restore, but it belongs in a written procedure.

---

## Step 3 — Backend cross-cutting concerns (2026-07-18)

**Checked and clean:**
- **Campaign scoping is airtight.** Of 198 API operations, 175 are campaign-scoped and
  every one sits behind `require_campaign_role` (12 `editor` + 12 `viewer` router-level
  dependencies); **zero** routes take a `campaign_id` path parameter without the guard.
  The 23 global operations are all legitimately global (shared catalogs: spells,
  equipment-library, rule-systems; plus campaign list/create, backups, healthz).
  `deps.py` correctly returns **404 rather than 403** for non-membership so campaign
  existence isn't leaked.
- **Service/router layering is clean** — **zero** `HTTPException` raised in any service
  or engine module. Services raise domain exceptions; routers translate. Exactly the
  convention CLAUDE.md documents.
- **One session pattern.** 189 uses of `Depends(get_session)`; the only 4 direct
  `SessionLocal()` uses are startup lifespan, migrations, and scripts — all correct.
- **Config is clean**: pydantic-settings, `NEXUS_` env prefix, `.env` support,
  `lru_cache`d, localhost-bound by default with the posture documented inline.
- **Bootstrap is properly idempotent** — get-or-create for the local user, the `dnd5e`
  rule system, and the demo campaign; safe to run on every start.
- **Request ceiling exists**: `MaxBodySizeMiddleware` rejects oversized
  `Content-Length` before the body is read, with the chunked-request gap documented.
- **Exception swallowing is mostly narrow and deliberate**: 17 silent sites, of which
  13 are tight `json.JSONDecodeError`/`ValueError` guards returning a default. Only 4
  are broad `except Exception` — two are the AUD-011 backups, one is a documented
  fresh-DB probe, one is `travel.py:336` (logged as AUD-001 item 13).

---

## Open findings

### AUD-001 · P1 · Backend has no logging setup and no coverage at the seams
- **Step:** scoping; **inventory completed in step 3**
- **Where:** `backend/app/` — exactly **one** `logging.getLogger` in the whole backend
  (`core/event_bus.py`), and **zero** logging configuration: no `basicConfig`,
  `dictConfig`, level setting, or file sink anywhere.
- **What:** Nothing the app does is recorded. Uvicorn's root config is the only reason
  the single existing `logger.exception` surfaces at all, there is no log file, and no
  `NEXUS_LOG_LEVEL` knob. Unhandled exceptions do get a uvicorn traceback, but with no
  request context (which campaign, which route, what payload). This is the single
  biggest supportability gap and the root cause of the "silent failure" theme running
  through steps 0–3.

**Logging inventory (the step-3 deliverable — build the fix from this list):**

| # | Seam | Where | Level | Why |
|---|---|---|---|---|
| 1 | Logging setup itself | `main.py` + `core/config.py` | — | `dictConfig`, `NEXUS_LOG_LEVEL`, console + rotating file sink |
| 2 | Request/response | new middleware | INFO / WARN / ERROR | method, path, status, duration, campaign_id; 5xx with traceback + request context |
| 3 | **Pre-migration backup failure** | `core/migrations.py:49` | ERROR | AUD-011 — currently silent |
| 4 | **Session-start backup failure** | `chronicle/service.py:202` | ERROR | AUD-011 — currently silent |
| 5 | Migrations applied | `core/migrations.py` | INFO | which revisions ran, from → to |
| 6 | Bootstrap | `campaign/service.ensure_bootstrap` | INFO | first-run user/campaign/rule-system creation |
| 7 | Library + bestiary seeding | `equipment/library_seed*`, `rules/bestiary` | INFO | counts seeded/skipped at startup |
| 8 | Command rollback | `core/pipeline.py:161` | ERROR | the `except: rollback; raise` path is invisible today |
| 9 | Projector failure | `core/projections.run_projectors` | ERROR | name the failing projector + event before the tx dies |
| 10 | Backup create / prune / restore | `backup/service.py` | INFO | what was written, what was rotated away |
| 11 | Archive import/export | `archive/service.py` | INFO/WARN | volume, and any partially-imported record |
| 12 | 5etools import skips | `import5e/monsters.py:70,74,281`, `tags.py:96` | WARN | malformed entries are silently dropped today |
| 13 | Polygon parse failure | `playbook/travel.py:336` | WARN | broad `except Exception: pass` |
| 14 | Search reindex failure | `wiki/search.py` | ERROR | drift is otherwise undetectable (AUD-017) |

- **Suggested fix:** Implement 1 and 2 first (they give the most coverage per line),
  then 3/4 (which closes AUD-011), then the rest. A shared `DomainError` hierarchy
  (AUD-020) makes the 5xx-vs-4xx logging split fall out naturally.
- **Status:** open

### AUD-002 · P2 · Test files named by sprint, not by feature
- **Step:** scoping (mapping table produced in step 10)
- **Where:** `backend/tests/test_sprint2.py` … `test_sprint19.py` (18 files)
- **What:** Sprint-named tests document *when* code was written, not *what* it
  protects. Finding the tests for a feature requires archaeology; new tests for an old
  feature have no natural home, so coverage intent erodes.
- **Suggested fix:** Step 10 builds the sprint→feature mapping; a later batch
  renames/splits the files along feature lines (`test_combat.py`, `test_wiki.py`, …)
  without changing test bodies. **Deferred to step 10** — the mapping has to exist
  before the rename is safe.
- **Status:** open

### AUD-004 · P2 · Repo hygiene: uncommitted one-off scripts *(partially fixed)*
- **Step:** 0 — baseline
- **Where:** `backend/scripts/seed_cos_magic_items.py`,
  `backend/scripts/split_appendix_c_treasures.py`
- **What:** Two one-off seed/split scripts sit untracked. Remaining sub-item only.
  ✅ `frontend/tsconfig.app.tsbuildinfo` untracked via `git rm --cached` (it was
  already in `.gitignore`, which doesn't apply to already-tracked files).
  ⏭️ `Things to add in CoS/items.md` left in place — it is campaign content and the
  source for the seed scripts, so its location is a content-organization choice, not a
  defect to fix unilaterally.
- **Suggested fix:** Step 6 decides per script whether each becomes a documented CLI,
  a test fixture, or is deleted; commit or remove accordingly.
- **Status:** open (reduced scope)

### AUD-011 · P1 · Both automatic backups can fail silently
- **Step:** 1 — architecture
- **Where:** `app/core/migrations.py:49`, `app/modules/chronicle/service.py:202`
- **What:** The two safety-net backups — the **pre-migration** snapshot (FR-13.2, taken
  at "the moment the data is most at risk") and the **session-start** snapshot — are
  both wrapped in `except Exception: pass`. Nothing is logged, so a backup that has
  been failing for months looks identical to one succeeding: you would only discover
  it when you reached for a snapshot that was never written. The migrations.py comment
  claims the failure is "logged by uvicorn", which is not true — the exception is
  swallowed before anything can log it.
- **Suggested fix:** Keep both best-effort (they must not block startup or session
  start) but `logger.exception(...)` in each handler, and surface backup health in the
  UI or `/healthz`. Folds into AUD-001's logging work.
- **Status:** open

### AUD-012 · P2 · Import-linter contracts have a large blind spot
- **Step:** 1 — architecture
- **Where:** `backend/pyproject.toml` `[tool.importlinter]`
- **What:** The layers contract names only 9 of 13 modules — `equipment`, `merchant`,
  `spells`, and `import5e` appear in no layer, so their dependencies are entirely
  unconstrained. `app/archive/` and `app/backup/` sit outside `app/modules/`
  altogether, so *neither* the layers contract nor the "core is a leaf" contract
  (which forbids only `app.core → app.modules`) can see them. Roughly a third of the
  backend is unenforced, and `archive/` in particular reaches into 9 modules — it is
  the de-facto top layer but is not declared as one. This blind spot is what let
  AUD-013 through.
- **Suggested fix:** Add the missing modules to the layers contract (`merchant` sits
  above `equipment` and `playbook`; `spells` and `import5e` look independent), and
  either move `archive`/`backup` under `app/modules/` or add a contract covering
  `app.archive` and `app.backup` explicitly.
- **Status:** open

### AUD-013 · P2 · `app.core` is not a leaf — it imports `app.backup`
- **Step:** 1 — architecture
- **Where:** `app/core/migrations.py:44`
- **What:** `upgrade_to_head()` does a function-local
  `from app.backup import service as backup_service`. This breaks ADR-001's "core is a
  leaf" rule, and the deferred (function-local) form exists precisely because the
  top-level import would be a circular one — `core → backup → core`. The contract does
  not catch it only because `app.backup` lives outside `app/modules/` (AUD-012).
- **Suggested fix:** Invert the dependency — have the startup path (`main.py` lifespan)
  take the pre-migration backup and then call `migrations.upgrade_to_head()`, so core
  never reaches upward. Then extend the leaf contract to forbid
  `app.core → app.archive|app.backup`.
- **Status:** open

### AUD-014 · P2 · ADR-004's "no mutation without a domain event" is not upheld
- **Step:** 1 — architecture
- **Where:** whole backend; `app/modules/atlas/` is the clearest case;
  `core/pipeline.py` docstring
- **What:** ADR-004 invariant #1 is "No mutation without a domain event ('if it isn't
  in the log, it didn't happen')", and `pipeline.py` opens by calling `command_tx` "the
  *only* write path in the system". Neither is true: there are 98 direct `.commit()`
  calls against 49 `command_tx` uses. Emit-vs-commit by module:

  | module | `ctx.emit` | `.commit()` |
  |---|---|---|
  | atlas | **0** | 11 |
  | rules | 0 | 6 |
  | spells | 0 | 1 |
  | equipment | 2 | 11 |
  | merchant | 2 | 6 |
  | playbook | 7 | 33 |
  | wiki | 11 | 2 |

  Some of those commits are legitimately eventless infrastructure (seeding, catalog
  sync, search-index maintenance). But **atlas emits no events at all** — creating,
  moving, or deleting a map, marker, or region leaves no trace in the log. That is a
  whole bounded context missing from the timeline, and it silently degrades the
  features built on the log (history, session recaps, the AI-recap plan in docs/15).
  There is also no written criterion for *when* a mutation warrants an event, so a
  contributor adding an endpoint cannot tell which path to use.
- **Suggested fix:** Decide deliberately and write it down in docs/06: either narrow
  ADR-004 rule #1 to "every mutation of *campaign-visible domain state*" and list the
  eventless categories, or add events to atlas and the other gaps. Then correct the
  `pipeline.py` docstring, which currently overstates the invariant.
- **Status:** open

### AUD-020 · P2 · Every router hand-translates exceptions; no app-level handlers
- **Step:** 3 — cross-cutting concerns
- **Where:** all 15 routers; no `@app.exception_handler` anywhere
- **What:** There are ~126 `raise HTTPException` sites wrapped in ~180 `except` blocks,
  repeating the same translation in every router (`playbook/router.py` alone has 40 and
  58). The mapping is *already* consistent enough to be mechanical — `*NotFound(LookupError)`
  → 404 (40 of 41 sites), `*Error(ValueError)` → 422, conflict types → 409 — so three
  `@app.exception_handler` registrations on `LookupError` / a shared `DomainError` /
  a `ConflictError` base would delete nearly all of it and make the convention
  enforced-by-construction instead of by discipline.
- **Suggested fix:** Introduce `core/errors.py` with `DomainError`/`NotFoundError`/
  `ConflictError` bases, have the existing per-module exceptions inherit from them
  (they already subclass `ValueError`/`LookupError`, so this is additive), register
  handlers in `main.py`, and strip the try/except boilerplate router by router. Pairs
  naturally with AUD-021 and inventory item 2 of AUD-001.
- **Status:** open

### AUD-021 · P2 · The API declares no error responses, so the typed client is error-blind
- **Step:** 3 — cross-cutting concerns
- **Where:** `backend/openapi.json`; all routers
- **What:** Of 198 operations, **185 have a path parameter but declare no 404**, and
  *no* operation anywhere declares 403, 409, or the 413 the body-size middleware can
  return. The only error content shape in the entire schema is FastAPI's automatic
  `HTTPValidationError` (422). Since `openapi.json` is the source of truth that
  generates `frontend/src/api/schema.d.ts`, the frontend has no typed knowledge of any
  error it will actually receive — it cannot distinguish "campaign not found" from
  "forbidden" from "conflict" except by reading `response.status` by hand. That
  hollows out the type contract CI works hard to keep fresh, and it is why frontend
  error handling (step 8/9) has nothing to bind to.
- **Suggested fix:** Declare a shared `ErrorResponse` model and add `responses={...}`
  to the routers — cheapest via a shared dict constant per router, or automatically
  once AUD-020's handlers exist. Then regenerate `openapi.json` + `schema.d.ts`.
- **Status:** open

### AUD-022 · P3 · Two small status-code inconsistencies
- **Step:** 3 — cross-cutting concerns
- **Where:** `chronicle/router.py` (SessionError), `equipment/router.py`
- **What:** `SessionError` maps to **409 in three places and 422 in one** — the same
  domain error producing different client-visible semantics. Separately,
  `equipment/router.py` uses `HTTP_422_UNPROCESSABLE_ENTITY` while every other router
  uses `HTTP_422_UNPROCESSABLE_CONTENT`; identical numerically (Starlette aliases), but
  the inconsistency invites confusion when grepping.
- **Suggested fix:** Pick 409 for SessionError (it is a state conflict), standardise on
  one 422 constant. Both disappear naturally under AUD-020's central handlers.
- **Status:** open

### AUD-016 · P2 · `docs/05-database-schema.md` describes an obsolete schema
- **Step:** 2 — data layer
- **Where:** `docs/05-database-schema.md` vs the live schema
- **What:** The document is the design of record for the database, and roughly a third
  of the real schema is missing from it. **14 live tables are undocumented**:
  `equipment`, `equipment_library`, `item_ownership_history`, `merchant`,
  `merchant_stock`, `spell`, `skill_challenge`, `skill_challenge_run`, `random_table`,
  `combat_roll`, `entity_media`, `article_snapshot`, `location_connection`,
  `timeline_entity`. **5 documented tables no longer exist**: `faction`, `location`,
  `pc`, `event_entity`, `encounter_combatant` — the first three collapsed into the
  generic `entity` table, a significant modelling decision the doc still contradicts.
- **Suggested fix:** Regenerate the DDL section from the live schema and re-write the
  narrative around the generic-`entity` model. Step 12 will confirm the same pattern
  across the other 15 docs.
- **Status:** open

### AUD-017 · P3 · No repair path for the FTS search index
- **Step:** 2 — data layer
- **Where:** `app/modules/wiki/search.py`, `scripts/`
- **What:** Projections have a recovery hatch (`scripts/rebuild_projections.py`, plus a
  test that replay equals incremental). The search index has no equivalent: it is
  maintained incrementally in-transaction, and if it ever drifts — a crashed bulk
  import, data restored from an older backup, or a `Tag` rename (tag names are indexed
  into every tagged entity's FTS row, and renaming a tag does not reindex those
  entities) — the only remedy is hand-written SQL.
- **Suggested fix:** Add `scripts/rebuild_search_index.py` that truncates
  `entity_fts`/`entity_fts_map` and re-runs `reindex` over every live entity. Cheap to
  write, and it makes a class of "search is missing things" reports self-serve.
- **Status:** open

### AUD-018 · P3 · 33 foreign-key columns have no leading index
- **Step:** 2 — data layer
- **Where:** live schema (96 FK constraints total)
- **What:** SQLite does not auto-index foreign keys, so with `foreign_keys=ON` every
  delete of a parent row scans each referencing child table, and joins on these columns
  are scans too. Notable cases: `map_marker.target_entity_id`,
  `map_region.target_entity_id` (deleting an entity scans all markers/regions),
  `story_edge.from_node`/`to_node` (graph traversal), `timeline_entity.entity_id` and
  `timeline_entry.event_id` (timeline filtering), `item.current_location_id`.
  Separately, `link_type.campaign_id` is the one campaign-scoped column with no leading
  index, against the "every query is scoped by campaign_id" convention. Invisible at the
  current data scale (2,246 events), hence P3.
- **Suggested fix:** Add indexes for the FK columns that are actually joined or
  cascade-checked — measure first rather than blanket-indexing all 33.
- **Status:** open

### AUD-019 · P3 · SQLite-specific `rowid` leaks outside the isolation boundary
- **Step:** 2 — data layer
- **Where:** `app/modules/wiki/service.py:560` and `:581`
- **What:** NFR-5.2 / `search.py`'s docstring claim SQLite-specific SQL is isolated so a
  PostgreSQL port only swaps the search module. These two `ORDER BY` clauses use
  `text("article_snapshot.rowid DESC")` as a deterministic tiebreak; PostgreSQL has no
  `rowid`, so the portability claim is not quite true.
- **Suggested fix:** Tiebreak on an existing monotonic column (the snapshot's `id`,
  which is a sortable UUIDv7) instead of `rowid`.
- **Status:** open

### AUD-015 · P3 · Story activation can half-apply its consequences
- **Step:** 1 — architecture
- **Where:** `app/modules/story/consequences.py:60-82`, `story/service.py:236-256`
- **What:** Node activation commits first, then consequences run as separate
  transactions (a documented saga — they call other services). Only
  `QuestError`/`NpcError` are caught, so any other exception (e.g. a `KeyError` from a
  consequence dict missing `quest_id`, or a DB error) propagates *after* the node is
  already committed `active` and after earlier consequences have applied — leaving a
  partially-applied activation with no compensating event. `validate()` guards
  well-formedness at write time, so this needs malformed or hand-edited data to
  trigger, hence P3.
- **Suggested fix:** Catch broadly in the consequence loop (the log-and-skip path
  already exists), and document the partial-application semantics in docs/06 — right
  now the code comment claims activation "never half-applies then explodes", which is
  the opposite of what the narrow `except` allows.
- **Status:** open

### AUD-009 · P3 · Frontend ships as a single 1.29 MB JS chunk
- **Step:** 0 — baseline
- **Where:** `npm run build` output (`dist/assets/index-*.js`, 381 kB gzipped)
- **What:** Everything (Leaflet, reactflow, dagre, TipTap, all features) loads up
  front. For a local single-user tool this is tolerable, which is why it's P3.
- **Suggested fix:** Lazy-load the heavy feature routes (atlas/map, story graph, wiki
  editor) with dynamic imports. Revisit after the audit completes.
- **Status:** open

---

## Fixed — batch 1 (2026-07-18)

Verified green across the full check suite and exercised in the running app before
removal from the open list.

### AUD-003 · P2 · No CLAUDE.md / agent onboarding file — **fixed**
Wrote [CLAUDE.md](../../CLAUDE.md): project layout, commands, the openapi type-contract
workflow, the import-linter boundary rules (with the amended layer order), house
conventions, and a pointer to this audit.

### AUD-005 · P0 · Backend toolchain ran from the old `DnD_Tracker` venv — **fixed**
The repo was copied from `C:\Users\shawn\DnD_Tracker` with `.venv` included, so the
console-script launchers (`pytest.exe`, `mypy.exe`, `lint-imports.exe`) still embedded
shebangs pointing at the **old** interpreter — every local backend check was validating
the old copy of the app, and pytest failed collection on modules that only exist in the
new tree. The **running dev server was also executing the old interpreter**
(`DnD_Tracker\...\python.exe` hosting `Campaign_Nexus\...\uvicorn.exe`).
Fixed by deleting `backend/.venv` and re-running `uv sync`, plus clearing stale
`__pycache__` dirs (which held cpython-310 bytecode from the old machine setup).
Verified: launcher shebangs now point at `Campaign_Nexus`, and plain `uv run pytest`
passes 410 tests.
**Follow-up left to the user:** rename or archive `C:\Users\shawn\DnD_Tracker` so
nothing can silently resolve to it again.

### AUD-006 · P1 · CI red — committed code failed ruff and eslint — **fixed**
`ruff check --fix` cleared 96 of 99 (72× `Optional[X]`→`X | None`, import sorting,
etc.). The remaining three were judgment calls: an unused `commit` assignment in
`test_travel_presets.py` (dropped, call kept); and two RUF001 "ambiguous Unicode"
hits on *intentional typography* in user-facing prose — the `×` in a purchase message
(inline `noqa` documenting intent) and an en dash in a seed item's range "5–45 ft"
(per-file ignore for `library_seed*.py`, since those files are entirely game prose).
The eslint error was a trailing `_childMapName` param; since the `_`-prefix convention
is already used in ~18 places, the fix codifies it via
`@typescript-eslint/no-unused-vars` `argsIgnorePattern: '^_'` rather than deleting a
param that documents the callback signature.

### AUD-007 · P1 · 9 mypy-strict errors, two of them real bugs — **fixed**
- `merchant/service.py:150` — sort key called `.name` on `session.get(...)` which can
  return `None` (latent `AttributeError`). Now reuses the file's existing `_name_of`
  helper, matching house style.
- `merchant/service.py:206` — `MerchantStock.__table__.delete()`; replaced with the
  SQLAlchemy 2.0 `delete(MerchantStock).where(...)` form.
- `main.py:152` — real namespace collision: `import app.modules.equipment.projectors`
  bound the name `app` to the *package*, colliding with `app = create_app()`. Switched
  to the `from … import projectors as _equipment_projectors  # noqa: F401` form and
  restored the explanatory comment (ruff's RUF100 autofix had stripped it). Verified
  live that the equipment library still seeds and serves, so the side effect survives.
- `rules/systems/dnd5e/__init__.py:530` — re-annotated `result` in one scope; dropped
  the duplicate annotation (both branches are live code, not dead).
- 5× `import5e` Any-leaks (`sources.py`, `copyres.py`, `spells.py` ×2, `monsters.py`)
  — narrowed with `isinstance` guards, an explicit `str | None` annotation, and one
  `cast` on the trusted JSON loader.

### AUD-010 · P3 · `openapi.json` was permanently "modified" after every export — **fixed**
Found while reviewing the working tree. `scripts/export_openapi.py` wrote the file with
Windows CRLF line endings while `.gitattributes` mandates LF, so `git status` flagged
the file as modified after every regeneration even when the content was identical —
noise that trains you to ignore a file CI treats as a contract. Fixed by passing
`newline=""` to suppress translation. Verified: regenerating now leaves the tree clean.

### AUD-008 · P2 · Module-boundary contract broken: playbook → atlas — **fixed**
`playbook/travel.py` imports `atlas.models` to resolve a location entity to map
coordinates. Rather than paper over it with an `ignore_imports` entry, the dependency
graph was checked: `atlas` depends only on `campaign` + `wiki`, and nothing but
`playbook` depends on `atlas`. The contract's "independent siblings" assumption simply
went stale once party position became map-aware, so the layer order now places `atlas`
below `playbook`, with a comment explaining the direction. All 3 contracts pass.

*Note for step 1: the layers contract does not list `equipment`, `merchant`, or
`spells` at all, so those modules are currently unconstrained by it.*
