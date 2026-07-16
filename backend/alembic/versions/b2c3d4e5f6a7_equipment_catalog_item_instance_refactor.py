"""equipment catalog + item instance refactor

Supersedes a1b2c3d4e5f6 (which conflated definition + instance into one table).

Changes:
  - Drop item_ownership_history (FK dep on item)
  - Drop item (old conflated table)
  - Create equipment (wiki-backed definition; no holder/location columns)
  - Create item (instance copies; FK to equipment, plain UUID PK)
  - Re-create item_ownership_history (FK now -> item.id not entity.id)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-15 11:00:00.000000
"""

from __future__ import annotations
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Drop old tables (history first — FK dependency)
    # ------------------------------------------------------------------
    with op.batch_alter_table('item_ownership_history') as batch_op:
        batch_op.drop_index('ix_item_ownership_history_item_id')
        batch_op.drop_index('ix_item_ownership_history_campaign_id')
    op.drop_table('item_ownership_history')

    with op.batch_alter_table('item') as batch_op:
        batch_op.drop_index('ix_item_current_holder_id')
        batch_op.drop_index('ix_item_current_holder_type')
        batch_op.drop_index('ix_item_rarity')
        batch_op.drop_index('ix_item_item_type')
        batch_op.drop_index('ix_item_campaign_id')
    op.drop_table('item')

    # ------------------------------------------------------------------
    # 2. Create equipment (catalog definition — entity-backed)
    # ------------------------------------------------------------------
    op.create_table(
        'equipment',
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('campaign_id', sa.String(), nullable=False),
        sa.Column('item_type', sa.String(), nullable=False),
        sa.Column('rarity', sa.String(), nullable=True),
        sa.Column('requires_attunement', sa.Integer(), nullable=False),
        sa.Column('value_gp', sa.String(), nullable=True),
        sa.Column('weight_lb', sa.Float(), nullable=True),
        sa.Column('properties', sa.Text(), nullable=True),
        sa.Column('attunement_notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entity_id'], ['entity.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('entity_id'),
    )
    with op.batch_alter_table('equipment') as batch_op:
        batch_op.create_index('ix_equipment_campaign_id', ['campaign_id'], unique=False)
        batch_op.create_index('ix_equipment_item_type', ['item_type'], unique=False)
        batch_op.create_index('ix_equipment_rarity', ['rarity'], unique=False)

    # ------------------------------------------------------------------
    # 3. Create item (instance copies — plain UUID PK)
    # ------------------------------------------------------------------
    op.create_table(
        'item',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('equipment_id', sa.String(), nullable=False),
        sa.Column('campaign_id', sa.String(), nullable=False),
        sa.Column('instance_label', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('current_holder_type', sa.String(), nullable=True),
        sa.Column('current_holder_id', sa.String(), nullable=True),
        sa.Column('current_location_id', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['current_holder_id'], ['entity.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['current_location_id'], ['entity.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipment.entity_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('item') as batch_op:
        batch_op.create_index('ix_item_campaign_id', ['campaign_id'], unique=False)
        batch_op.create_index('ix_item_equipment_id', ['equipment_id'], unique=False)
        batch_op.create_index('ix_item_current_holder_type', ['current_holder_type'], unique=False)
        batch_op.create_index('ix_item_current_holder_id', ['current_holder_id'], unique=False)

    # ------------------------------------------------------------------
    # 4. Re-create item_ownership_history (FK -> item.id)
    # ------------------------------------------------------------------
    op.create_table(
        'item_ownership_history',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('campaign_id', sa.String(), nullable=False),
        sa.Column('item_id', sa.String(), nullable=False),
        sa.Column('holder_type', sa.String(), nullable=True),
        sa.Column('holder_id', sa.String(), nullable=True),
        sa.Column('location_id', sa.String(), nullable=True),
        sa.Column('from_game', sa.Integer(), nullable=False),
        sa.Column('to_game', sa.Integer(), nullable=True),
        sa.Column('cause_event_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['item_id'], ['item.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['location_id'], ['entity.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('item_ownership_history') as batch_op:
        batch_op.create_index('ix_item_ownership_history_campaign_id', ['campaign_id'], unique=False)
        batch_op.create_index('ix_item_ownership_history_item_id', ['item_id'], unique=False)


def downgrade() -> None:
    # Drop new tables
    with op.batch_alter_table('item_ownership_history') as batch_op:
        batch_op.drop_index('ix_item_ownership_history_item_id')
        batch_op.drop_index('ix_item_ownership_history_campaign_id')
    op.drop_table('item_ownership_history')

    with op.batch_alter_table('item') as batch_op:
        batch_op.drop_index('ix_item_current_holder_id')
        batch_op.drop_index('ix_item_current_holder_type')
        batch_op.drop_index('ix_item_equipment_id')
        batch_op.drop_index('ix_item_campaign_id')
    op.drop_table('item')

    with op.batch_alter_table('equipment') as batch_op:
        batch_op.drop_index('ix_equipment_rarity')
        batch_op.drop_index('ix_equipment_item_type')
        batch_op.drop_index('ix_equipment_campaign_id')
    op.drop_table('equipment')

    # Restore old item table (definition + instance merged)
    op.create_table(
        'item',
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('campaign_id', sa.String(), nullable=False),
        sa.Column('item_type', sa.String(), nullable=False),
        sa.Column('rarity', sa.String(), nullable=True),
        sa.Column('requires_attunement', sa.Integer(), nullable=False),
        sa.Column('value_gp', sa.String(), nullable=True),
        sa.Column('weight_lb', sa.String(), nullable=True),
        sa.Column('properties', sa.Text(), nullable=True),
        sa.Column('attunement_notes', sa.Text(), nullable=True),
        sa.Column('current_holder_type', sa.String(), nullable=True),
        sa.Column('current_holder_id', sa.String(), nullable=True),
        sa.Column('current_location_id', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['current_holder_id'], ['entity.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['current_location_id'], ['entity.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['entity_id'], ['entity.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('entity_id'),
    )
    with op.batch_alter_table('item') as batch_op:
        batch_op.create_index('ix_item_campaign_id', ['campaign_id'], unique=False)
        batch_op.create_index('ix_item_item_type', ['item_type'], unique=False)
        batch_op.create_index('ix_item_rarity', ['rarity'], unique=False)
        batch_op.create_index('ix_item_current_holder_type', ['current_holder_type'], unique=False)
        batch_op.create_index('ix_item_current_holder_id', ['current_holder_id'], unique=False)

    op.create_table(
        'item_ownership_history',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('campaign_id', sa.String(), nullable=False),
        sa.Column('item_id', sa.String(), nullable=False),
        sa.Column('holder_type', sa.String(), nullable=True),
        sa.Column('holder_id', sa.String(), nullable=True),
        sa.Column('location_id', sa.String(), nullable=True),
        sa.Column('from_game', sa.Integer(), nullable=False),
        sa.Column('to_game', sa.Integer(), nullable=True),
        sa.Column('cause_event_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['item_id'], ['entity.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['location_id'], ['entity.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('item_ownership_history') as batch_op:
        batch_op.create_index('ix_item_ownership_history_campaign_id', ['campaign_id'], unique=False)
        batch_op.create_index('ix_item_ownership_history_item_id', ['item_id'], unique=False)
