# Development

Campaign Nexus is a modular monolith: a FastAPI backend (`backend/`) and a React +
TypeScript frontend (`frontend/`). See [docs/](docs/) for the full design;
[Sprint plan](docs/12-roadmap.md) tracks what each sprint delivers.

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node 20+ and npm

## Backend

```sh
cd backend
uv sync                      # install deps into .venv
uv run alembic upgrade head  # create/upgrade the SQLite schema
uv run uvicorn app.main:app --reload   # http://127.0.0.1:8000  (docs at /docs)
```

On first start the app bootstraps a local user and a demo campaign (local-first,
single-user posture — ADR-011). The database file (`campaign_nexus.db`) is git-ignored.

### Backend checks (what CI runs)

```sh
uv run ruff check .        # lint
uv run mypy app            # strict type-check
uv run lint-imports        # module-boundary contracts (ADR-001)
uv run pytest              # tests
uv run python -m scripts.export_openapi   # regenerate backend/openapi.json
```

## Frontend

```sh
cd frontend
npm install
npm run gen:api            # regenerate the typed client from backend/openapi.json
npm run dev                # http://localhost:5200 (proxies /api to the backend)
```

Start the backend first — the dev server proxies `/api` to `127.0.0.1:8000`.

### Frontend checks

```sh
npm run lint
npm run typecheck
npm run build
```

## The type contract

`backend/openapi.json` is the source of truth for the API shape. The backend generates
it; the frontend generates its TypeScript client from it (`npm run gen:api`). CI fails
if either is stale, so backend/frontend drift is caught at build time (NFR-4.3).
Workflow when you change an endpoint:

1. Edit the backend, run `python -m scripts.export_openapi`.
2. Run `npm run gen:api` in the frontend.
3. Commit both regenerated files with your change.

## Architecture guardrails (enforced in CI)

- **Core is a leaf** — `app.core` must never import `app.modules`.
- **Module layering** — feature modules (`wiki`, `chronicle`) are independent of each
  other and may only depend downward on `campaign` (the scoping context) and `core`.
- **One write path** — every mutation goes through `command_tx` and emits a domain event
  (ADR-004). Direct table writes outside a command handler are a review failure.

## Sprint 1 status

Walking skeleton complete: command pipeline + domain event log, entity registry with an
atomic `POST /entities`, Alembic migrations, the React shell with a generated typed
client, and green CI gates. Exit criteria verified in `backend/tests/` and by the
end-to-end UI check (create an entity → event committed atomically).
