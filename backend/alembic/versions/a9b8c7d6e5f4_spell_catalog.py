"""spell catalog (global reference)

Adds the campaign-independent ``spell`` table backing the shared spell reference.
Content is imported at runtime (scripts/import_5etools.py); no data ships in the repo.

Revision ID: a9b8c7d6e5f4
Revises: 0a052984255d
Create Date: 2026-07-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a9b8c7d6e5f4'
down_revision: str | None = '0a052984255d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'spell',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('school', sa.String(), nullable=True),
        sa.Column('casting_time', sa.String(), nullable=True),
        sa.Column('range_text', sa.String(), nullable=True),
        sa.Column('component_v', sa.Integer(), nullable=False),
        sa.Column('component_s', sa.Integer(), nullable=False),
        sa.Column('component_m', sa.Integer(), nullable=False),
        sa.Column('material', sa.Text(), nullable=True),
        sa.Column('concentration', sa.Integer(), nullable=False),
        sa.Column('ritual', sa.Integer(), nullable=False),
        sa.Column('classes', sa.String(), nullable=True),
        sa.Column('duration', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('higher_levels', sa.Text(), nullable=True),
        sa.Column('damage_types', sa.String(), nullable=True),
        sa.Column('saving_throw', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('spell') as batch_op:
        batch_op.create_index('ix_spell_name', ['name'], unique=False)
        batch_op.create_index('ix_spell_source', ['source'], unique=False)
        batch_op.create_index('ix_spell_level', ['level'], unique=False)
        batch_op.create_index('ix_spell_school', ['school'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('spell') as batch_op:
        batch_op.drop_index('ix_spell_school')
        batch_op.drop_index('ix_spell_level')
        batch_op.drop_index('ix_spell_source')
        batch_op.drop_index('ix_spell_name')
    op.drop_table('spell')
