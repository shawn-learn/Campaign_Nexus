"""equipment: item and item_ownership_history tables

Revision ID: a1b2c3d4e5f6
Revises: 07dc0c8ea602
Create Date: 2026-07-15 10:22:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '07dc0c8ea602'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
    with op.batch_alter_table('item', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_item_campaign_id'), ['campaign_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_item_item_type'), ['item_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_item_rarity'), ['rarity'], unique=False)
        batch_op.create_index(batch_op.f('ix_item_current_holder_type'), ['current_holder_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_item_current_holder_id'), ['current_holder_id'], unique=False)

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
    with op.batch_alter_table('item_ownership_history', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_item_ownership_history_campaign_id'), ['campaign_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_item_ownership_history_item_id'), ['item_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('item_ownership_history', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_item_ownership_history_item_id'))
        batch_op.drop_index(batch_op.f('ix_item_ownership_history_campaign_id'))

    op.drop_table('item_ownership_history')

    with op.batch_alter_table('item', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_item_current_holder_id'))
        batch_op.drop_index(batch_op.f('ix_item_current_holder_type'))
        batch_op.drop_index(batch_op.f('ix_item_rarity'))
        batch_op.drop_index(batch_op.f('ix_item_item_type'))
        batch_op.drop_index(batch_op.f('ix_item_campaign_id'))

    op.drop_table('item')
