"""atlas: entity_media (entity image attachments)

Revision ID: b7c2e9f4a1d3
Revises: e1b152f089e5
Create Date: 2026-07-11 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c2e9f4a1d3'
down_revision: str | None = 'e1b152f089e5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('entity_media',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('campaign_id', sa.String(), nullable=False),
    sa.Column('entity_id', sa.String(), nullable=False),
    sa.Column('media_id', sa.String(), nullable=False),
    sa.Column('caption', sa.String(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at_real', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['entity_id'], ['entity.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['media_id'], ['media.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('entity_media', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_entity_media_campaign_id'), ['campaign_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_entity_media_entity_id'), ['entity_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('entity_media', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_entity_media_entity_id'))
        batch_op.drop_index(batch_op.f('ix_entity_media_campaign_id'))

    op.drop_table('entity_media')
