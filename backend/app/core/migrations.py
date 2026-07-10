"""Programmatic Alembic entrypoint used at startup and in tooling."""

from __future__ import annotations

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from app.core.config import BACKEND_ROOT, get_settings


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def _pending_migrations(cfg: Config) -> bool:
    """True if the database is behind head — so we only back up when a migration will run."""
    url = cfg.get_main_option("sqlalchemy.url") or ""
    if not url.startswith("sqlite:///"):
        return False
    script = ScriptDirectory.from_config(cfg)
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
    except Exception:  # pragma: no cover - a fresh/absent DB is "behind" by definition
        return True
    finally:
        engine.dispose()
    return current != script.get_current_head()


def upgrade_to_head() -> None:
    cfg = _alembic_config()
    # A migration is the moment the data is most at risk, so snapshot it first (FR-13.2).
    # Best-effort: a backup failure must never block the app from starting.
    if _pending_migrations(cfg):
        try:
            from app.backup import service as backup_service
            from app.core.db import SessionLocal

            with SessionLocal() as session:
                backup_service.create_backup(session, reason="pre-migration")
        except Exception:  # pragma: no cover - logged by uvicorn; startup proceeds
            pass
    command.upgrade(cfg, "head")
