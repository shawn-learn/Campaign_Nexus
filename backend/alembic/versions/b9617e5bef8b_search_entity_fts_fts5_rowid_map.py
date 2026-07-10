"""search: entity_fts (FTS5) + rowid map

Revision ID: b9617e5bef8b
Revises: cca2652c918f
Create Date: 2026-07-08 19:51:30.405324
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'b9617e5bef8b'
down_revision: str | None = 'cca2652c918f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite-specific FTS5 index (kept portable behind app.modules.wiki.search; NFR-5.2).
    op.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS entity_fts USING fts5("
        "  entity_id UNINDEXED, campaign_id UNINDEXED,"
        "  name, summary, article_text, tags,"
        "  tokenize='unicode61 remove_diacritics 2')"
    )
    op.execute(
        "CREATE TABLE IF NOT EXISTS entity_fts_map("
        "  entity_id TEXT PRIMARY KEY, rowid INTEGER NOT NULL)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS entity_fts")
    op.execute("DROP TABLE IF EXISTS entity_fts_map")
