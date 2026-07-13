"""playbook: skill_challenge + skill_challenge_run

Revision ID: c3f1a9e28b47
Revises: b7c2e9f4a1d3
Create Date: 2026-07-12 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c3f1a9e28b47'
down_revision: str | None = 'b7c2e9f4a1d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'skill_challenge',
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('campaign_id', sa.String(), nullable=False),
        sa.Column('premise', sa.Text(), nullable=True),
        sa.Column('total_checks', sa.Integer(), nullable=False),
        sa.Column('success_target', sa.Integer(), nullable=True),
        sa.Column('failure_cap', sa.Integer(), nullable=True),
        sa.Column('approaches_json', sa.Text(), nullable=False),
        sa.Column('outcomes_json', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entity_id'], ['entity.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('entity_id'),
    )
    with op.batch_alter_table('skill_challenge', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_skill_challenge_campaign_id'), ['campaign_id'], unique=False
        )

    op.create_table(
        'skill_challenge_run',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('campaign_id', sa.String(), nullable=False),
        sa.Column('challenge_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('checks_json', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['challenge_id'], ['skill_challenge.entity_id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('skill_challenge_run', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_skill_challenge_run_campaign_id'), ['campaign_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('skill_challenge_run', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_skill_challenge_run_campaign_id'))
    op.drop_table('skill_challenge_run')

    with op.batch_alter_table('skill_challenge', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_skill_challenge_campaign_id'))
    op.drop_table('skill_challenge')
