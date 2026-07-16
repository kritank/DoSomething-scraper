"""add_health_and_queue_snapshots

Revision ID: d7f3b1e4a682
Revises: c1d4a8f92b57
Create Date: 2026-07-17 09:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7f3b1e4a682'
down_revision: Union[str, None] = 'c1d4a8f92b57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'credential_health_snapshots',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('platform', sa.String(length=16), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('failure_count', sa.Integer(), nullable=False),
        sa.Column('quota_used_today', sa.Integer(), nullable=True),
        sa.Column('instagram_account_id', sa.UUID(), nullable=True),
        sa.Column('youtube_api_key_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['instagram_account_id'], ['instagram_accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['youtube_api_key_id'], ['youtube_api_keys.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_credential_health_snapshots_snapshot_at'), 'credential_health_snapshots', ['snapshot_at'], unique=False)
    op.create_index(op.f('ix_credential_health_snapshots_platform'), 'credential_health_snapshots', ['platform'], unique=False)
    op.create_index(op.f('ix_credential_health_snapshots_instagram_account_id'), 'credential_health_snapshots', ['instagram_account_id'], unique=False)
    op.create_index(op.f('ix_credential_health_snapshots_youtube_api_key_id'), 'credential_health_snapshots', ['youtube_api_key_id'], unique=False)

    op.create_table(
        'queue_depth_snapshots',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('backend', sa.String(length=16), nullable=False),
        sa.Column('main_depth', sa.Integer(), nullable=True),
        sa.Column('dlq_depth', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_queue_depth_snapshots_snapshot_at'), 'queue_depth_snapshots', ['snapshot_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_queue_depth_snapshots_snapshot_at'), table_name='queue_depth_snapshots')
    op.drop_table('queue_depth_snapshots')

    op.drop_index(op.f('ix_credential_health_snapshots_youtube_api_key_id'), table_name='credential_health_snapshots')
    op.drop_index(op.f('ix_credential_health_snapshots_instagram_account_id'), table_name='credential_health_snapshots')
    op.drop_index(op.f('ix_credential_health_snapshots_platform'), table_name='credential_health_snapshots')
    op.drop_index(op.f('ix_credential_health_snapshots_snapshot_at'), table_name='credential_health_snapshots')
    op.drop_table('credential_health_snapshots')
