"""equipment.weight_lb String -> Float

The catalog refactor (b2c3d4e5f6a7) originally declared ``weight_lb`` as a String
column while the model typed it ``float``. Correct the affinity so numeric
storage, sorting, and filtering behave. Idempotent: a no-op where the column is
already REAL.

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-07-15 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c4d5e6f7a8b9'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('equipment') as batch_op:
        batch_op.alter_column(
            'weight_lb',
            existing_type=sa.String(),
            type_=sa.Float(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table('equipment') as batch_op:
        batch_op.alter_column(
            'weight_lb',
            existing_type=sa.Float(),
            type_=sa.String(),
            existing_nullable=True,
        )
