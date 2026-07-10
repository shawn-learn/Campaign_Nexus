"""Alembic environment — targets Base.metadata with every model imported."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from app.core.config import get_settings
from app.db_metadata import metadata  # imports all models as a side effect
from sqlalchemy import engine_from_config, pool

config = context.config
# The app's settings own the database URL — except when a caller passes one explicitly
# (``alembic -x url=…``, or the migration tests, which upgrade a throwaway database).
_url_override = context.get_x_argument(as_dictionary=True).get("url")
config.set_main_option("sqlalchemy.url", _url_override or get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def include_name(name: str | None, type_: str, _parent: object) -> bool:
    # The FTS5 search index and its shadow tables are managed by app.modules.wiki.search,
    # not ORM metadata; keep autogenerate from trying to drop/recreate them.
    return not (type_ == "table" and name is not None and name.startswith("entity_fts"))


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # SQLite-safe ALTERs
        compare_type=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
