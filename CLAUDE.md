# Campaign Nexus — working notes for Claude

A GM's campaign operating system: FastAPI modular monolith + React/TypeScript SPA,
local-first and single-user (players never touch it). `docs/01`–`16` are the design of
record; [DEVELOPMENT.md](DEVELOPMENT.md) is the human setup guide.

## Layout

```
backend/app/core/      leaf primitives: db, ids, clock, config, money, dice,
                       event_bus, domain_event, pipeline, projections, migrations
backend/app/modules/   bounded contexts (campaign, wiki, time, rules, chronicle,
                       atlas, npcs, playbook, story, equipment, merchant, spells,
                       import5e) — each: models / schemas / router / service
backend/app/archive/   campaign export/import      backend/app/backup/   snapshots
backend/alembic/       migrations (linear chain)   backend/scripts/      CLI tools + seeds
frontend/src/api/      client.ts + hooks.ts + schema.d.ts (generated — never hand-edit)
frontend/src/features/ one dir per feature, mirrors the backend contexts
frontend/src/shell/    layout, nav, command palette   stores/  Zustand (client state only)
```

## Commands

Backend (from `backend/`, all via `uv run`):

```sh
uv sync                      # install deps
uv run ruff check .          # lint            (--fix to autofix)
uv run mypy app              # strict types
uv run lint-imports          # module boundaries — see below
uv run pytest                # 410 tests, ~50s
uv run alembic upgrade head  # apply migrations
```

Frontend (from `frontend/`):

```sh
npm run lint · typecheck · test · build
npm run dev                  # :5200, proxies /api to :8000
```

Run the whole app: `python start.py` from the repo root (backend :8000 + frontend :5200).

## The type contract — the one workflow that bites

`backend/openapi.json` is the source of truth for the API shape. After **any** endpoint
or schema change:

```sh
cd backend  && uv run python -m scripts.export_openapi   # regenerate openapi.json
cd frontend && npm run gen:api                           # regenerate schema.d.ts
```

Commit both. CI fails if either is stale.

## Module boundaries (ADR-001)

`import-linter` contracts in `backend/pyproject.toml` are enforced in CI:

- `app.core` is a leaf — it must never import `app.modules`.
- Modules are layered (top → bottom): `story` → `playbook | npcs` → `atlas` →
  `chronicle` → `wiki | time` → `rules` → `campaign`. Imports may only point *down*.
- No module may import `rules.systems.*` directly — game systems are reached only
  through `rules.registry`.

Cross-context *reactions* go through `core/event_bus.py`, not direct calls. If you need
a new upward or sideways import, that is a design decision: change the layer order with
a comment explaining why, don't quietly add an `ignore_imports` entry.

## Conventions

- Python 3.12+, `from __future__ import annotations`, full type annotations (mypy
  strict). Line length 100.
- Services hold the logic; routers stay thin. Domain errors are exception subclasses
  (`MerchantNotFound`, …) that routers translate to HTTP.
- Every query is scoped by `campaign_id`.
- A leading `_` marks a deliberately unused binding (Python and TypeScript both).
- SQLite: WAL mode, FTS5 for search, JSON1 for flexible columns; schema is kept
  PostgreSQL-portable.

## Audit in progress

`docs/audit/AUDIT_PLAN.md` is a 14-step supportability audit; findings accumulate in
`docs/audit/FINDINGS.md`. To run one: "Run audit step N from docs/audit/AUDIT_PLAN.md".
Audit steps are findings-only — they don't change code.
