"""equipment library (global templates) + equipment.library_id provenance

Adds the campaign-independent ``equipment_library`` table and a nullable
``library_id`` on ``equipment`` recording which template a campaign definition
was imported from.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-15 13:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd5e6f7a8b9c0'
down_revision: str | None = 'c4d5e6f7a8b9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'equipment_library',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('item_type', sa.String(), nullable=False),
        sa.Column('rarity', sa.String(), nullable=True),
        sa.Column('requires_attunement', sa.Integer(), nullable=False),
        sa.Column('value_gp', sa.String(), nullable=True),
        sa.Column('weight_lb', sa.Float(), nullable=True),
        sa.Column('properties', sa.Text(), nullable=True),
        sa.Column('attunement_notes', sa.Text(), nullable=True),
        sa.Column('source', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('equipment_library') as batch_op:
        batch_op.create_index('ix_equipment_library_name', ['name'], unique=False)
        batch_op.create_index('ix_equipment_library_item_type', ['item_type'], unique=False)
        batch_op.create_index('ix_equipment_library_rarity', ['rarity'], unique=False)
        batch_op.create_index('ix_equipment_library_source', ['source'], unique=False)

    with op.batch_alter_table('equipment') as batch_op:
        batch_op.add_column(sa.Column('library_id', sa.String(), nullable=True))
        batch_op.create_index('ix_equipment_library_id', ['library_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_equipment_library_id', 'equipment_library', ['library_id'], ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('equipment') as batch_op:
        batch_op.drop_constraint('fk_equipment_library_id', type_='foreignkey')
        batch_op.drop_index('ix_equipment_library_id')
        batch_op.drop_column('library_id')

    with op.batch_alter_table('equipment_library') as batch_op:
        batch_op.drop_index('ix_equipment_library_source')
        batch_op.drop_index('ix_equipment_library_rarity')
        batch_op.drop_index('ix_equipment_library_item_type')
        batch_op.drop_index('ix_equipment_library_name')
    op.drop_table('equipment_library')
