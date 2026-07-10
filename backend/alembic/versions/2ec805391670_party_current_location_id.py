"""party current_location_id

Revision ID: 2ec805391670
Revises: cd9294f53ab3
Create Date: 2026-07-10 06:57:13.512906

Hand-adjusted: SQLite has no ALTER for constraints, so alembic rewrites the table in "batch"
mode — and a batch-mode constraint must be named. Autogenerate emitted ``None``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '2ec805391670'
down_revision: str | None = 'cd9294f53ab3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK = "fk_party_current_location_entity"


def upgrade() -> None:
    with op.batch_alter_table('party', schema=None) as batch_op:
        batch_op.add_column(sa.Column('current_location_id', sa.String(), nullable=True))
        batch_op.create_foreign_key(
            _FK, 'entity', ['current_location_id'], ['id'], ondelete='SET NULL'
        )


def downgrade() -> None:
    with op.batch_alter_table('party', schema=None) as batch_op:
        batch_op.drop_constraint(_FK, type_='foreignkey')
        batch_op.drop_column('current_location_id')
