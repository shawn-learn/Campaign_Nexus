"""Database engine, session factory, and the declarative ORM base.

SQLite is configured per ADR-002: WAL journal (readers don't block the single
writer) and enforced foreign keys. These pragmas are applied on every new
connection via an event listener so they hold for pooled connections too.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Single declarative base — its metadata is the target for Alembic autogenerate.

    Feature modules import this base and register their tables against it; importing
    ``app.core.db`` (a core module) never pulls in feature code, preserving the
    ADR-001 dependency direction.
    """


def _make_engine() -> Engine:
    settings = get_settings()
    is_sqlite = settings.database_url.startswith("sqlite")
    engine = create_engine(
        settings.database_url,
        # check_same_thread=False lets the dev server share the connection across
        # threads; writes remain serialized by SQLite itself (single-writer model).
        connect_args={"check_same_thread": False} if is_sqlite else {},
        future=True,
    )
    if is_sqlite:
        _install_sqlite_pragmas(engine)
    return engine


def _install_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


engine: Engine = _make_engine()
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False, future=True
)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
