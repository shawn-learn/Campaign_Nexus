"""merchant + merchant_stock

Shops (entity-backed, type 'merchant') and their for-sale inventory lines drawn
from the equipment library.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-07-15 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e6f7a8b9c0d1'
down_revision: str | None = 'd5e6f7a8b9c0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'merchant',
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('campaign_id', sa.String(), nullable=False),
        sa.Column('npc_id', sa.String(), nullable=True),
        sa.Column('location_id', sa.String(), nullable=True),
        sa.Column('buyback_pct', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entity_id'], ['entity.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['npc_id'], ['entity.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['location_id'], ['entity.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('entity_id'),
    )
    with op.batch_alter_table('merchant') as batch_op:
        batch_op.create_index('ix_merchant_campaign_id', ['campaign_id'], unique=False)
        batch_op.create_index('ix_merchant_npc_id', ['npc_id'], unique=False)
        batch_op.create_index('ix_merchant_location_id', ['location_id'], unique=False)

    op.create_table(
        'merchant_stock',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('merchant_id', sa.String(), nullable=False),
        sa.Column('campaign_id', sa.String(), nullable=False),
        sa.Column('library_id', sa.String(), nullable=False),
        sa.Column('price_cp', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['merchant_id'], ['merchant.entity_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['library_id'], ['equipment_library.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('merchant_stock') as batch_op:
        batch_op.create_index('ix_merchant_stock_merchant_id', ['merchant_id'], unique=False)
        batch_op.create_index('ix_merchant_stock_campaign_id', ['campaign_id'], unique=False)
        batch_op.create_index('ix_merchant_stock_library_id', ['library_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('merchant_stock') as batch_op:
        batch_op.drop_index('ix_merchant_stock_library_id')
        batch_op.drop_index('ix_merchant_stock_campaign_id')
        batch_op.drop_index('ix_merchant_stock_merchant_id')
    op.drop_table('merchant_stock')

    with op.batch_alter_table('merchant') as batch_op:
        batch_op.drop_index('ix_merchant_location_id')
        batch_op.drop_index('ix_merchant_npc_id')
        batch_op.drop_index('ix_merchant_campaign_id')
    op.drop_table('merchant')
