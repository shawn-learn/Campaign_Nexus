"""party.gold (gp) -> party.wealth_cp (copper)

Track wealth in the smallest coin so sp/cp are exact. Existing gp balances are
converted (gold * 100).

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-16 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f7a8b9c0d1e2'
down_revision: str | None = 'e6f7a8b9c0d1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('party') as batch_op:
        batch_op.add_column(sa.Column('wealth_cp', sa.Integer(), nullable=False, server_default='0'))
    op.execute('UPDATE party SET wealth_cp = gold * 100')
    with op.batch_alter_table('party') as batch_op:
        batch_op.drop_column('gold')


def downgrade() -> None:
    with op.batch_alter_table('party') as batch_op:
        batch_op.add_column(sa.Column('gold', sa.Integer(), nullable=False, server_default='0'))
    op.execute('UPDATE party SET gold = wealth_cp / 100')
    with op.batch_alter_table('party') as batch_op:
        batch_op.drop_column('wealth_cp')
