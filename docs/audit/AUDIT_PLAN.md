# Campaign Nexus — Supportability & Quality Audit Playbook

A deep-dive audit of the whole application, broken into 14 session-sized steps so every
pass is thorough. Each step is self-contained: scope, checklist, exit criteria.

## How to run

In any session, say: **"Run audit step N from docs/audit/AUDIT_PLAN.md"**.
One or two steps per session — the whole point of the decomposition is that no step is
ever rushed. Steps 0–13 can run in any order, though 0 should run first (it records the
baseline everything else compares against). Step 14 runs last.

## Rules (all steps)

- **Findings only.** Audit steps never change source code, config, or data. Running
  checks, tests, and read-only scripts is allowed and expected. Fixes happen later, in
  prioritized batches after step 14.
- **Everything is logged.** Each issue found becomes an entry in
  [FINDINGS.md](FINDINGS.md) with the next free `AUD-NNN` id, the step number, a
  severity (P0–P3, defined in FINDINGS.md), file/location, description, and a suggested
  fix. If a step finds nothing in some checklist area, note that too — "checked, clean"
  is a result.
- **Exit criteria.** A step is done when every checklist item was examined and its
  findings (or a clean bill) are logged. If a step runs long, stop at a checklist
  boundary and note in FINDINGS.md which items remain.
- **Benchmarks.** `docs/01`–`16` are the design of record; DEVELOPMENT.md and CI
  (`.github/workflows/ci.yml`) define the expected developer workflow. Deviations from
  either are findings (sometimes the right fix is updating the doc — log it anyway).

---

## Step 0 — Baseline health & repo hygiene

**Scope:** whole repo, no source dirs in depth.

**Checklist:**
- [ ] Run every backend CI check locally and record pass/fail + timing:
      `uv run ruff check .`, `uv run mypy app`, `uv run lint-imports`, `uv run pytest`
      (from `backend/`).
- [ ] OpenAPI freshness: `uv run python -m scripts.export_openapi`, then check
      `git diff backend/openapi.json` is empty; `npm run gen:api` then check
      `git diff frontend/src/api/schema.d.ts` is empty.
- [ ] Run every frontend check: `npm run lint`, `npm run typecheck`, `npm test`,
      `npm run build` (from `frontend/`); record pass/fail + timing.
- [ ] Compare the local check set against `.github/workflows/ci.yml` — does CI actually
      run everything DEVELOPMENT.md claims it runs?
- [ ] Repo hygiene: review `git status` — every modified/untracked file should be
      explainable (work in progress) or a finding (strays like
      `Things to add in CoS/items.md`, tracked build artifacts like
      `frontend/tsconfig.app.tsbuildinfo`).
- [ ] `.gitignore` audit: db files (`campaign_nexus.db*`), `backups/`, `media/`,
      `*.tsbuildinfo`, caches — ignored where they should be, and nothing important
      ignored by accident.
- [ ] `backend/scripts/` inventory: classify each script (repeatable tool vs one-off
      seed vs dead); flag one-offs that should be documented, promoted, or deleted.

**Exit:** baseline table (check → result → time) recorded in FINDINGS.md; hygiene
findings logged.

---

## Step 1 — Architecture & module boundaries

**Scope:** `backend/app/core/` (all files), `backend/app/main.py`,
`backend/pyproject.toml` (import-linter contracts), `docs/03-adr.md`,
`docs/04-domain-model.md`, `docs/06-event-sourcing.md`.

**Checklist:**
- [ ] Verify the three import-linter contracts still describe the intended design;
      check whether `ignore_imports` exceptions (cos_weather → time) are growing or
      should be resolved properly.
- [ ] Cross-context communication: confirm reactions really go through
      `core/event_bus.py` — grep for direct cross-module imports or service calls that
      sidestep it.
- [ ] `core/domain_event.py` + `core/event_bus.py`: handler registration, error
      handling inside handlers (does one failing projector poison the write?),
      idempotency, ordering guarantees.
- [ ] `core/projections.py` + `scripts/rebuild_projections.py`: can every projection be
      rebuilt from the event log? Are projectors (`modules/*/projectors.py`) pure
      functions of events?
- [ ] `core/pipeline.py`: transaction boundaries — is event append + projection update
      atomic? What happens on partial failure?
- [ ] `core/db.py`, `core/ids.py`, `core/clock.py`, `core/config.py`,
      `core/migrations.py`, `core/money.py`, `core/dice.py`, `core/calendars.py`:
      each still cohesive, leaf-level (no `app.modules` imports), and used consistently
      (e.g. no module minting ids or reading the clock its own way).
- [ ] `app/archive/` and `app/backup/` sit outside `app/modules/` — deliberate and
      documented, or drift?
- [ ] Reality vs `docs/06-event-sourcing.md`: which aggregates are actually
      event-sourced vs plain CRUD, and does the doc say so?

**Exit:** boundary violations, event-bus gaps, and doc drift logged.

---

## Step 2 — Data layer

**Scope:** `backend/alembic/` (32 versions), `backend/app/core/db.py`,
`backend/app/core/migrations.py`, `backend/app/db_metadata.py`, all
`modules/*/models.py`, `docs/05-database-schema.md`, `backend/tests/test_migrations.py`.

**Checklist:**
- [ ] Migration chain: single linear history (`alembic history`), no branches; clean
      `alembic upgrade head` against an empty scratch DB (use a temp file, not
      `campaign_nexus.db`).
- [ ] Models↔migrations drift: run `alembic revision --autogenerate` against the temp
      DB and confirm the diff is empty (delete the scratch revision afterwards — it is
      a scratch artifact, not a source change).
- [ ] SQLite pragmas: WAL mode, `foreign_keys=ON` enforced on *every* connection
      (engine event, not one-off), busy timeout.
- [ ] Indexing: FK columns and common query predicates indexed; compare against
      `docs/05-database-schema.md`; flag doc drift.
- [ ] FTS5: which tables are indexed, how are they kept in sync (triggers vs app code),
      any injection or corruption risk in the sync path.
- [ ] JSON columns: where is `JSON1` relied on; is schema-in-JSON validated
      (`jsonschema` is a dependency — used where?).
- [ ] File-adjacent data: lifecycle of `backend/media/` and `backend/backups/` —
      orphan files when rows are deleted? referenced files that can go missing?
- [ ] PostgreSQL portability claim (README): spot-check for SQLite-only constructs
      outside the pragmas layer.

**Exit:** schema, migration, and integrity findings logged.

---

## Step 3 — Backend cross-cutting concerns

**Scope:** every `modules/*/router.py` and `modules/*/service.py` skimmed for the
*patterns* below (deep per-module reads happen in steps 4–6); `backend/app/main.py`,
`core/config.py`, `modules/campaign/deps.py`, `backend/tests/test_request_limits.py`.

**Checklist:**
- [ ] Error handling: one consistent way of raising HTTP errors? Consistent error
      response shape? Do services raise domain exceptions that routers translate, or
      `HTTPException` from the bowels?
- [ ] Status codes: 404 vs 422 vs 409 used consistently across modules for the same
      situations (missing entity, validation, conflict).
- [ ] Session/transaction management: one dependency pattern for DB sessions;
      commit/rollback in one place; no `commit()` scattered mid-service.
- [ ] Campaign scoping: is every query scoped by campaign id via a shared dependency
      (`campaign/deps.py`), or do some endpoints trust client-supplied ids?
- [ ] Validation depth: Pydantic schemas actually constrain (lengths, ranges, enums) or
      mostly `str`/`int` passthrough?
- [ ] Request limits: what `test_request_limits.py` covers; body-size and
      list-pagination limits at the app level.
- [ ] Startup/bootstrap (`main.py`): first-run user+demo-campaign bootstrap — is it
      idempotent, migration-safe, and does failure leave a usable state?
- [ ] Config: everything through pydantic-settings? env var names documented? secrets
      story (even local-first, the posture should be stated).
- [ ] **Logging (pre-seeded AUD-001):** confirm the extent of the gap; inventory what
      *should* be logged (requests, event-bus dispatch, projector failures, migrations,
      backup/restore) as input to the fix batch.

**Exit:** cross-cutting inconsistencies logged with representative examples (not an
exhaustive enumeration — the pattern plus 2–3 instances each).

---

## Step 4 — Backend deep dive: gameplay engine

**Scope:** `backend/app/modules/playbook/` (router.py 919 lines, combat.py,
combat_reducer.py, dashboard.py, encounters.py, quests.py, tables.py,
skill_challenges.py, travel.py, models.py, schemas.py 709 lines, service.py),
`backend/app/modules/rules/` (+ `systems/dnd5e/`, `systems/nimble/`,
`systems/simpletest.py`), `docs/08-rules-engine.md`, related tests
(`test_dice.py`, `test_dnd5e_plugin.py`, `test_random_tables.py`,
`test_skill_challenges.py`, `test_travel_*.py`, sprint tests touching combat).

**Checklist (apply to each file):**
- [ ] Router/service/schema layering: business logic leaking into the 919-line
      router.py? Candidates for splitting along the existing sub-files?
- [ ] Combat event sourcing: `combat_reducer.py` vs frontend
      `frontend/src/lib/combatReducer.ts` — same reduction semantics? Undo/redo
      correctness; what happens on unknown/legacy event types in old combats.
- [ ] Rules plugin seam (`rules/interface.py`, `rules/registry.py`): does the dnd5e
      plugin (778 lines) leak system-specific types upward? Is nimble actually complete
      or a stub? Is `simpletest.py` production code or test scaffolding in prod tree?
- [ ] Query efficiency: N+1 patterns in encounter/combat/dashboard composite reads.
- [ ] Dead code and stale TODOs across the module.
- [ ] Schema quality: the 709-line schemas.py — duplication with models, unvalidated
      free-form dicts.

**Exit:** per-file findings logged; explicit note for combat parity result.

---

## Step 5 — Backend deep dive: world & narrative

**Scope:** `backend/app/modules/wiki/` (service.py 778 lines), `atlas/`
(incl. imagesize.py, entity_media_router.py), `npcs/`, `chronicle/`, `time/`
(calendar.py, scheduled.py), `campaign/` (incl. cos_weather.py, flags.py), `story/`
(conditions.py, consequences.py), `docs/07-time-engine.md`, related tests
(`test_calendar.py`, `test_time_realtime.py`, `test_cos_weather.py`,
`test_entities_*.py`, `test_edit_endpoints.py`).

**Checklist (apply to each module):**
- [ ] Same layering/dead-code/N+1/validation checks as step 4.
- [ ] Wiki: the 778-line service — entity/article/relations responsibilities separable?
      Mention/backlink integrity when entities are renamed or deleted.
- [ ] Knowledge graph: typed edge table + recursive CTEs — cycle handling, orphan
      edges on delete.
- [ ] Time engine: calendar math correctness vs `docs/07`; scheduled-event firing
      (missed events on clock jumps? travel/rest integration).
- [ ] Chronicle: timeline reset is destructive — guarded how? What exactly is deleted
      vs preserved?
- [ ] Story: `conditions.py`/`consequences.py` evaluate cross-module state — via the
      sanctioned downward imports only? Failure mode when a referenced quest/NPC/flag
      is gone.
- [ ] `campaign/cos_weather.py` + the import-linter exceptions: campaign-specific
      content living in a core module — belongs elsewhere?
- [ ] Atlas media: upload validation (`imagesize.py`), content-type checks, filename
      handling on `entity_media_router.py` (path traversal checked here, not step 13).
- [ ] Projectors (`chronicle/projectors.py`, `npcs/projectors.py`): rebuildable, pure,
      registered once.

**Exit:** per-module findings logged.

---

## Step 6 — Backend deep dive: content & lifecycle

**Scope:** `backend/app/modules/equipment/` (incl. library_seed.py,
library_seed_phb.py, library_seed_cos.py), `merchant/` (incl. money.py — vs
`core/money.py`!), `spells/`, `import5e/` (all 9 files), `app/archive/`,
`app/backup/`, `backend/scripts/` (all 15 scripts), related tests
(`test_equipment*.py`, `test_merchant.py`, `test_spells.py`, `test_import5e.py`,
`test_import_export.py`, `test_bestiary_upgrade.py`).

**Checklist:**
- [ ] Same layering/dead-code/N+1/validation checks as step 4.
- [ ] Duplication: `merchant/money.py` vs `core/money.py` — two money
      implementations?
- [ ] Seed/library data: how large are `library_seed*.py`, are they idempotent, and is
      copyrighted game content (PHB/CoS) handled per an explicit policy?
- [ ] `import5e/`: robustness against malformed 5etools input; partial-import failure
      behavior (transaction? resumable?).
- [ ] Export/import (`archive/`): round-trip fidelity — does `test_import_export.py`
      prove export→import→export is stable? Media included? Cross-campaign id
      collisions?
- [ ] Backup (`backup/` + `scripts/restore_backup.py`): what a backup contains (db +
      media?), restore path exercised by a test or only by hand, WAL handling during
      backup.
- [ ] `backend/scripts/`: for each script — does it still run? does it mutate prod data
      without confirmation? should it be a documented CLI, a test fixture, or deleted?

**Exit:** findings logged; explicit verdicts for money duplication, backup restore, and
round-trip fidelity.

---

## Step 7 — API contract & conventions

**Scope:** `backend/openapi.json`, all `modules/*/router.py` signatures,
`docs/10-api-design.md`, `frontend/src/api/client.ts`, DEVELOPMENT.md type-contract
section.

**Checklist:**
- [ ] Resource naming, nesting, and verb conventions vs `docs/10` — list deviations.
- [ ] Composite read endpoints: which exist, are they documented, do they duplicate
      finer-grained endpoints?
- [ ] Error responses: uniform shape in openapi.json, or per-router improvisation?
- [ ] Pagination/sorting/filtering: one convention across list endpoints?
- [ ] Contract workflow drift traps: what happens when someone edits an endpoint and
      forgets `export_openapi` + `gen:api` — CI catches it (verify the actual CI step),
      but is the failure message actionable?
- [ ] Response-model discipline: endpoints returning ORM objects or untyped dicts
      instead of declared schemas.
- [ ] Versioning/deprecation posture: stated anywhere? (Local-first single-user makes
      this cheap — but the posture should be a sentence in docs/10, not implicit.)

**Exit:** convention deviations logged with endpoint examples.

---

## Step 8 — Frontend architecture

**Scope:** `frontend/src/api/client.ts`, `frontend/src/api/hooks.ts` (3,043 lines),
`frontend/src/stores/` (campaign.ts, ui.ts, recents.ts), `frontend/src/router.tsx`,
`frontend/src/shell/` (Layout.tsx, CampaignSwitcher, CommandPalette, EntityPeek,
ClockWidget, NotificationsWidget, useActiveCampaign), `frontend/src/lib/`,
`docs/09-ui-architecture.md`.

**Checklist:**
- [ ] `hooks.ts` at 3k lines: organization (one file for every feature's hooks?),
      naming conventions, and whether it should split per-feature.
- [ ] Query-key discipline: consistent key factory? Invalidation after mutations —
      spot-check 5–6 mutations for missing/over-broad invalidation.
- [ ] State ownership: Zustand stores hold only client state (active campaign, UI,
      recents) and never mirror server data? Any duplicated server state?
- [ ] Router: route definitions vs `shell/Layout.tsx` nav vs CommandPalette — three
      lists that must agree; do they?
- [ ] `client.ts`: error handling on non-2xx (surfaced to UI how?), base-URL/proxy
      assumptions, campaign-id injection.
- [ ] `lib/` utilities: calendar.ts duplicating backend calendar math — parity test
      exists (`calendar.test.ts`) and covers the same cases as backend
      `test_calendar.py`?
- [ ] Cross-feature consistency: pick three features (one old, e.g. wiki; one mid,
      e.g. playbook; one new, e.g. story) and compare page structure, data-fetch
      patterns, and error handling — is there one house style?

**Exit:** architecture findings logged, including a recommendation on hooks.ts split.

---

## Step 9 — Frontend component quality

**Scope:** largest components — `features/atlas/MapCanvasComponents.tsx` (932),
`features/equipment/EquipmentPage.tsx` (912), `features/merchants/MerchantsPage.tsx`
(499), `features/playbook/CombatPage.tsx` (497), `features/wiki/EntityDetailPage.tsx`
(437) — plus a sample of mid-size pages, `frontend/src/components/` (shared),
`frontend/src/styles.css`.

**Checklist:**
- [ ] Decomposition: for each large component, is it large because it does many things
      (split candidate) or one irreducible thing? Concrete split seams.
- [ ] Hooks correctness: effect dependency honesty, state derived-not-stored,
      stale-closure hazards in the map/combat interaction code.
- [ ] Loading/error/empty states: every `useQuery` consumer renders all three? List
      the ones that render only the happy path.
- [ ] Shared components (`Modal`, `Tabs`, `ListToolbar`, `SearchableSelect`): used
      everywhere the pattern appears, or re-implemented ad hoc in places?
- [ ] `styles.css` as a single file: size, dead selectors, naming convention, whether
      it is still navigable or needs per-feature organization.
- [ ] Accessibility basics: form inputs labelled, dialogs trap focus (`Modal.tsx`),
      keyboard path through CommandPalette and combat tracker, icon-only buttons have
      accessible names.

**Exit:** per-component findings logged with split seams named.

---

## Step 10 — Test suite quality

**Scope:** `backend/tests/` (43 files incl. `test_sprint2..19.py`, conftest.py,
fixtures/), frontend tests (`*.test.ts(x)` — 8 files, `src/test/setup.ts`),
`docs/14-testing-strategy.md`, CI workflow.

**Checklist:**
- [ ] Measure backend coverage (`uv run pytest --cov=app` — add pytest-cov as a
      *temporary* tool if absent; do not commit config) and record per-module numbers.
- [ ] Measure frontend coverage (`vitest run --coverage`) and record.
- [ ] Map each `test_sprintN.py` to the features it actually tests (pre-seeded
      AUD-002): produce the mapping table — it is the input for a later rename/reorg
      batch.
- [ ] Untested critical paths: combat engine (backend reducer + frontend reducer +
      undo/redo), story conditions/consequences, time engine edge cases (leap
      handling, clock jumps), export/import round-trip, backup/restore, migration
      upgrade path.
- [ ] Test quality sample: pick 5 tests — do they assert behavior or implementation?
      Would they survive a refactor?
- [ ] Fixture health: `conftest.py` + `fixtures/` — one blessed way to build a
      campaign/entity, or copy-paste setup in every file?
- [ ] Speed & flake: total wall time (from step 0 baseline), any sleeps/real-clock
      dependence (`test_time_realtime.py` is a suspect by name).
- [ ] Reality vs `docs/14-testing-strategy.md`: which promised suites/tiers exist.

**Exit:** coverage numbers, sprint→feature map, and critical-path gap list logged.

---

## Step 11 — Supportability & operations

**Scope:** DEVELOPMENT.md, README.md, `.github/workflows/ci.yml`, `backend/app/main.py`
bootstrap, `core/config.py`, backup/restore path, absence of CLAUDE.md (pre-seeded
AUD-003).

**Checklist:**
- [ ] Cold-start walkthrough: follow DEVELOPMENT.md verbatim in a scratch clone
      (read-only w.r.t. the real repo) — every command works, every prerequisite
      stated, first-run bootstrap succeeds. Log each deviation.
- [ ] Debuggability story: when something fails at runtime, where does the operator
      look? (Currently: uvicorn stderr and nothing else — quantify what AUD-001's fix
      must cover: request logs, event dispatch, projector errors, slow queries.)
- [ ] Failure surfaces: what the *user* sees when the backend is down, a request 500s,
      or the DB is locked — blank page, toast, or silence?
- [ ] Data safety runbook: is there a written procedure for backup, restore, and the
      destructive chronicle reset? Exercise restore against a scratch DB.
- [ ] Upgrade path: what happens to an existing `campaign_nexus.db` when the app
      updates (migrations run when, exactly?); is downgrade explicitly unsupported and
      said so?
- [ ] Environment drift: Python/Node version pins (pyproject `>=3.12`, CI matrix, `uv.lock`,
      `package-lock.json`) all agree?
- [ ] CLAUDE.md: absent — draft its outline (project map, commands, contract workflow,
      conventions) as a finding so the fix batch can write it.

**Exit:** walkthrough log + runbook gaps recorded.

---

## Step 12 — Docs drift

**Scope:** all 16 docs in `docs/`, README.md.

**Checklist:** for each doc, sample-check 3–5 concrete claims against the code and mark
the doc **current / drifted / aspirational**:
- [ ] 01-prd, 02-requirements: scope claims vs shipped features (README says through
      Sprint 19).
- [ ] 03-adr: every ADR still true? (ADR-001 boundaries, ADR-011 local-first posture —
      cross-check with steps 1 and 13 results if available.)
- [ ] 04-domain-model: bounded contexts vs actual `app/modules/` list (archive/backup
      outside modules/, story added).
- [ ] 05-database-schema: DDL vs live schema (reuse step 2 result if done).
- [ ] 06-event-sourcing, 07-time-engine, 08-rules-engine: mechanisms vs
      implementation.
- [ ] 09-ui-architecture: stack and navigation model vs `router.tsx`/`shell/`.
- [ ] 10-api-design: conventions vs step 7 findings.
- [ ] 11-security-model: posture vs reality (single-user local — does the doc admit
      what is deferred?).
- [ ] 12-roadmap, 16-mvp-definition: sprint claims vs git history spot-check.
- [ ] 13-risk-register: risks still live? new risks this audit surfaced that belong
      there?
- [ ] 14-testing-strategy: vs step 10 findings. 15-future-enhancements: anything in it
      already built?

**Exit:** per-doc verdict table logged; drifted sections enumerated.

---

## Step 13 — Dependencies & security posture

**Scope:** `backend/pyproject.toml` + `uv.lock`, `frontend/package.json` +
`package-lock.json`, `docs/11-security-model.md`, upload/serve paths
(`atlas/entity_media_router.py`, backup endpoints), FTS query construction.

**Checklist:**
- [ ] `uv run pip-audit` (or `uv tool run pip-audit`) and `npm audit` — record CVEs,
      classify exploitable-in-posture vs not.
- [ ] Outdated majors: `uv tree`/`npm outdated` — flag majors behind (React 18 vs 19,
      Vite 6 vs 7, etc.) with upgrade-risk notes, not upgrade commands.
- [ ] Posture check scaled to ADR-011 (local-first, single user, players never touch
      it): what is the actual listen address (localhost-only?), CORS config, and does
      `docs/11` state the trust boundary honestly?
- [ ] File serving: media and backup download endpoints — path traversal, content-type
      sniffing, size limits on upload.
- [ ] Raw SQL inventory: every `text()`/f-string SQL (FTS queries are the likely spot)
      — parameterized?
- [ ] Backup restore trust: restoring a backup executes nothing? (zip/tar extraction
      paths, alembic downgrade on restore of older schema).
- [ ] Licenses: game content (PHB/CoS seeds) and dependency licenses — any
      distribution concern if the repo goes public.

**Exit:** vulnerability + posture findings logged with exploitability-in-context noted.

---

## Step 14 — Consolidated report

**Scope:** `docs/audit/FINDINGS.md` (everything logged by steps 0–13).

**Checklist:**
- [ ] Dedupe: merge findings that share a root cause; keep one id, note the merged ids.
- [ ] Re-rank with full knowledge: severities assigned early may change once patterns
      are visible.
- [ ] Produce the remediation backlog: fix batches sized for one session each,
      ordered P0 → P1 → high-value P2; each batch lists its finding ids and a
      verification step.
- [ ] Explicitly recommend which P2/P3 findings to *accept* (wontfix with a reason) —
      an audit that turns everything into work items has failed at prioritizing.
- [ ] Write the executive summary at the top of FINDINGS.md: overall verdict on
      supportability, the three most important themes, and the recommended batch order.

**Exit:** FINDINGS.md is the single, prioritized source of truth; fixing begins with
"Fix batch 1 from docs/audit/FINDINGS.md".
