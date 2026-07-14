"""Test harness: an isolated temp SQLite DB, schema via metadata (no Alembic in tests)."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

# Point the app at a throwaway database *before* app modules read settings. Media and
# backups go to temp dirs too, so nothing leaks into the repo tree during a test run.
_TMP_ROOT = Path(tempfile.gettempdir()) / "campaign_nexus_test"
_TMP_ROOT.mkdir(exist_ok=True)
_TMP_DB = _TMP_ROOT / "campaign_nexus_test.db"
os.environ["NEXUS_DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"
os.environ.setdefault("NEXUS_MEDIA_DIR", str(_TMP_ROOT / "media"))
os.environ.setdefault("NEXUS_BACKUP_DIR", str(_TMP_ROOT / "backups"))

import pytest  # noqa: E402
from app.core import migrations  # noqa: E402
from app.core.db import SessionLocal, engine  # noqa: E402
from app.db_metadata import metadata  # noqa: E402
from app.modules.wiki import search as wiki_search  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

# Tests own the schema lifecycle via create_all/drop_all; stub the startup migration.
migrations.upgrade_to_head = lambda: None  # type: ignore[assignment]


@pytest.fixture
def db() -> Iterator[Session]:
    engine.dispose()
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        metadata.drop_all(conn)
        metadata.create_all(conn)
        # FTS tables aren't part of ORM metadata; reset and recreate them explicitly.
        conn.execute(text("DROP TABLE IF EXISTS entity_fts"))
        conn.execute(text("DROP TABLE IF EXISTS entity_fts_map"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
    session = SessionLocal()
    wiki_search.ensure_search_schema(session)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as test_client:  # triggers lifespan → bootstrap
        yield test_client
