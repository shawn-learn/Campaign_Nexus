"""time: scheduled_event + campaign_flag

Revision ID: 9a7c1cab5430
Revises: b9617e5bef8b
Create Date: 2026-07-08 20:14:59.494056
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9a7c1cab5430'
down_revision: str | None = 'b9617e5bef8b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'campaign_flag',
        sa.Column('campaign_id', sa.String(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value_json', sa.Text(), nullable=False),
        sa.Column('updated_at_game', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('campaign_id', 'key'),
    )
    op.create_table(
        'scheduled_event',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('campaign_id', sa.String(), nullable=False),
        sa.Column('fire_at_game', sa.Integer(), nullable=False),
        sa.Column('recurrence_days', sa.Integer(), nullable=True),
        sa.Column('action_type', sa.String(), nullable=False),
        sa.Column('action_json', sa.Text(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('created_by_kind', sa.String(), nullable=False),
        sa.Column('source_entity_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('scheduled_event', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_scheduled_event_campaign_id'), ['campaign_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('scheduled_event', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_scheduled_event_campaign_id'))
    op.drop_table('scheduled_event')
    op.drop_table('campaign_flag')
