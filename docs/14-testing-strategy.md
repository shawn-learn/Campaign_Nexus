# 18. Testing Strategy

Solo-developer reality shapes this strategy: tests are the only reviewer that never sleeps.
Budget: ~30% of implementation time, spent where regressions are most expensive — the engines
and the write pipeline — not on UI snapshot churn.

## 18.1 The pyramid (and what lives at each level)

```
        E2E (Playwright)         ~15 golden journeys
      ───────────────────
      API / integration          every endpoint happy-path + authz + key errors
    ───────────────────────      (FastAPI TestClient on real SQLite, in-memory)
    Engine & property tests      the crown jewels — see 18.3
  ───────────────────────────
  Unit (pure logic)              calendar math, reducers, DSL, link diffing, validators
```

## 18.2 Foundations

- **Backend:** pytest; every test runs on a real SQLite database (`:memory:` or tmp file with
  WAL) — no mocking of the DB, ever; SQLite is fast enough that realism is free. Factory
  fixtures (`factory-boy`) per entity type; one `campaign` fixture with the demo seed.
- **Frontend:** Vitest + React Testing Library for logic-bearing components (editor mention
  sync, combat cards, advancement dialogs); MSW for API stubbing in component tests.
- **Static gates in CI (fail = red):** mypy --strict, ruff, eslint, tsc --noEmit,
  import-linter (module boundaries, no-`dnd5e`-in-core), OpenAPI→TS client freshness diff.
- Coverage is tracked but not worshipped; the enforced floor applies to `engine` packages
  (time, events, rules interface, combat reducer): **95% branch**.

## 18.3 Engine test suites (the crown jewels)

**Calendar math (Hypothesis property tests + golden files).**
Properties: `to_date(to_minutes(d)) == d` for all valid dates incl. festivals/leap days;
minutes monotonic ⇔ date ordering; season/moon functions total. Golden files: 200 known
Harptos dates. The same fixtures feed the TypeScript port — **parity is a build gate**.

**Advancement loop.**
Ordered-firing property (fired events sorted by `fire_at_game` regardless of insertion
order); recurrence chaining (event scheduling an event inside the window fires in-window);
runaway guard triggers; **atomicity fault-injection**: crash mid-loop (raised in a handler) ⇒
clock, events, projections all unchanged.

**Event pipeline & projections.**
The **rebuild oracle**: for every scenario test, run incrementally, snapshot projections;
then `rebuild-projections` from the event log; assert equality. This single pattern converts
every feature test into a dual-write-integrity test (mitigates R-4). Plus: every service
mutation emits ≥1 event (instrumented session assertion); compensating-event retraction
honored by projections.

**Combat reducer (twin parity).**
Shared JSON fixtures: `[initial_state, actions[]] → expected_state` — executed by pytest
against the Python reducer and by Vitest against the TS twin; a fixture-hash manifest keeps
the sets in lockstep. Property tests: undo^n then redo^n is identity; new action truncates
redo tail; fold is deterministic and order-stable.

**Rules plugin conformance kit.**
A reusable pytest suite parameterized over every installed plugin (`dnd5e`, `nimble`,
`simpletest`): schemas are valid JSON Schema; validate/derive round-trip on pack content;
rests return well-formed `StatusDelta`s; facets populate; layout spec renders in the generic
renderer (jsdom smoke). New plugin = inherit the kit for free; the kit **is** the interface's
executable spec (mitigates R-3).

**Condition DSL.** Parser fuzzing (no crash, no eval), golden ASTs, step-limit enforcement,
typecheck errors for unknown refs.

## 18.4 API / integration layer

Per endpoint: happy path, campaign-scope enforcement (member of campaign A requesting B's
resource → 404-as-403 policy), validation errors (RFC 9457 shape), optimistic-version
conflict, idempotency-key replay. Composite views (`/views/dashboard`, `/views/entity`)
get response-shape contract tests pinned to the OpenAPI schema.

## 18.5 E2E golden journeys (Playwright, against a built app + seeded DB)

The ~15 journeys mirror sprint exit criteria, e.g.: create campaign → first NPC via red link
→ backlink appears · @mention round-trip · ⌘K search-navigate-peek · advance 30 days with
festival recurrence → timeline check · long rest → HP/slots/clock · build encounter → run
combat with undo → timeline summary · map drill-down world→city→peek NPC · quest deadline
expiry · start/end live session → auto-links · export→import→verify. Run on CI nightly and
before any tagged build (they're minutes, not hours, at this app size).

## 18.6 Performance tests (NFR-1 as regression gates)

A generated **50k-entity / 500k-link / 1M-event fixture campaign** (deterministic seed) +
pytest-benchmark suite: search p95 < 100 ms · entity view < 200 ms · dashboard composite
< 200 ms · 30-day advancement firing 100 events < 1 s · rebuild-projections throughput
(informational). Run nightly; regressions >20% fail the build. Numbers recorded per release
(Sprint 20 exit).

## 18.7 Migration & data-safety tests

Every Alembic migration tested up **and** down against a snapshot of the previous release's
seeded DB; backup-before-migrate verified by the wrapper's own test; export→import round-trip
equality (projections rebuilt on both sides) is a release gate; a quarterly **restore drill**
from a timed backup is a checklist item, not a test — but it is on the checklist.

## 18.8 Dogfooding as a test tier

From Sprint 5, the developer's real campaign runs on latest `main` (with the backup system
watching). Real prep and real sessions surface the friction and semantics bugs no fixture
will. Bug triage rule: anything that interrupted a live session is P0 for the next sprint.
