# 17. Risk Register

Scored: Probability × Impact, 1–5 each. Reviewed at every phase boundary.

| ID | Risk | P | I | Score | Category |
|----|------|---|---|-------|----------|
| R-1 | **Time-engine complexity spiral** — calendars, recurrence, and the ordered firing loop hide corner cases (leap days, chained firings, huge jumps); the subsystem everything depends on ships late or flaky | 4 | 5 | 20 | Technical |
| R-2 | **Wiki friction kills adoption (by its own developer)** — if entity creation/linking feels slower than a text file, dogfooding stops and the product dies quietly | 3 | 5 | 15 | Product |
| R-3 | **Rules abstraction leaks 5e** — core quietly assumes slots/CR/6-second rounds; adding Nimble forces a rewrite | 4 | 4 | 16 | Technical |
| R-4 | **Dual-write discipline erodes** — a mutation path skips the event log; history/projections silently diverge (the hybrid model's known weakness, ADR-004) | 3 | 5 | 15 | Technical |
| R-5 | **Combat tracker too slow for the table** — >a few seconds per action and the GM reverts to pencil; reducer parity bugs cause optimistic-UI desyncs | 3 | 4 | 12 | Product |
| R-6 | **Map tiling pipeline rabbit hole** — image processing, memory, formats eat sprints for a feature that is "nice navigation," not core | 3 | 3 | 9 | Technical |
| R-7 | **Licensing misstep** — shipping non-SRD 5e content, mis-attributed CC-BY, or unlicensed Nimble material | 2 | 5 | 10 | Legal |
| R-8 | **Data loss incident** — SQLite corruption, bad migration, or user error destroys a campaign; trust is unrecoverable | 2 | 5 | 10 | Technical |
| R-9 | **Solo-developer scope creep / burnout** — a 9-subsystem product tempts endless polish; MVP slips past the motivation horizon | 4 | 4 | 16 | Delivery |
| R-10 | **Story engine over-automation** — auto-firing triggers wrest authorship from the GM, produce wrong world states, and demand undo machinery for narrative | 3 | 3 | 9 | Product |
| R-11 | **Search quality disappoints** — FTS5 defaults rank poorly for short fantasy names; ⌘K feels dumb | 2 | 3 | 6 | Technical |
| R-12 | **SQLite ceiling met early** — a future sharing/hosted push arrives before the PG port is practical | 1 | 4 | 4 | Strategic |

## Mitigations & owners (owner = the developer wearing the named hat)

**R-1 (20) — Time engine.** Build first among the engines (Phase 2); `CalendarMath` as a pure
module with property-based + golden tests before any UI; runaway guard + firing ceiling in the
loop from day one; "advance preview" UI de-risks GM surprise. *Contingency:* ship MVP with
interval recurrence only (calendar-rule recurrence in v1.0).

**R-2 (15) — Wiki friction.** Sprint-5 dogfood gate: if creating+linking an NPC takes >30 s,
stop feature work and fix. Red-link create-in-place, ⌘K everywhere, in-place editing
(§12.4) are non-negotiable scope. *Signal:* developer's own prep notes drifting back to
text files = alarm.

**R-3 (16) — 5e leakage.** `simpletest` stub system in CI from Sprint 9 — core tested against
two systems before 5e polish; import-linter forbids `dnd5e` imports outside the plugin;
§10.8's closed vocabulary is a review checklist item. *Contingency:* budgeted — Sprint 18
exists precisely to pay any remaining leakage down.

**R-4 (15) — Dual-write erosion.** Single `command_tx` pipeline is the only exposed write
API (repositories are module-private); CI test asserts every service mutation emits ≥1 event
(instrumented session); `rebuild-projections` diff run on the dogfood DB every sprint —
divergence caught in weeks, not years.

**R-5 (12) — Combat speed.** TS reducer twin with shared fixtures (parity is contract-tested,
§8.5); keyboard-first design tested against a stopwatch (Sprint 13 exit: full round of 10
combatants < 60 s of operator time); optimistic UI with server hash reconciliation.

**R-6 (9) — Map tiling.** Timebox: one sprint for the pipeline using boring tech
(libvips/pyvips, WebP tiles); cap source size (raise later); *fallback:* untiled single-image
Leaflet for maps ≤4k px — ships value even if the pyramid slips.

**R-7 (10) — Licensing.** SRD 5.1 under CC-BY-4.0 only, attribution screen in-app; Nimble
content contingent on written license review — else ship schemas + empty pack (§10.7 already
plans for this); no non-SRD names anywhere in fixtures or seeds (review checklist).

**R-8 (10) — Data loss.** WAL + `PRAGMA foreign_keys`; backup-before-migration automated in
the Alembic wrapper; rotating timed backups + session-start snapshot (NFR-2.2); soft delete;
export early (Sprint 19 pulled earlier if any incident occurs); *restore drill* is a Sprint-19
exit criterion, not a hope.

**R-9 (16) — Scope/burnout.** MVP gate is Sprint 14's "run a real session" — everything else
is negotiable; deferral list (MVP doc §16.4) is pre-agreed so cutting is a decision, not a
defeat; dogfooding keeps payoff visible; sprints end with tagged builds (momentum artifacts).
*Watch item:* any sprint that ends demo-less twice in a row triggers a scope review.

**R-10 (9) — Story over-automation.** MVP keeps the GM in the loop by design (suggestions
drawer, FR-4.4/4.5 split); consequences are a closed action catalog (§14.4); auto-firing
stays post-1.0 behind per-trigger opt-in.

**R-11 (6) — Search quality.** bm25 weights tuned (name ≫ summary ≫ body), prefix-boost on
name hits, recents in empty state; fixture-based relevance tests with a 5k-entity corpus.

**R-12 (4) — SQLite ceiling.** NFR-5.2 discipline (portable SQL, wrapped FTS/JSON usage) is
enforced now; PG port scoped as a bounded task in Future Enhancements; accept the risk.
