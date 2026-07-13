"""playbook: random_table

Revision ID: d4e2b7c91a05
Revises: c3f1a9e28b47
Create Date: 2026-07-12 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e2b7c91a05'
down_revision: str | None = 'c3f1a9e28b47'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'random_table',
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('campaign_id', sa.String(), nullable=False),
        sa.Column('dice', sa.String(), nullable=False),
        sa.Column('rows_json', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entity_id'], ['entity.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('entity_id'),
    )
    with op.batch_alter_table('random_table', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_random_table_campaign_id'), ['campaign_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('random_table', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_random_table_campaign_id'))
    op.drop_table('random_table')
