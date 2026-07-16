"""add_youtube_support

Revision ID: c5e8f2a91d47
Revises: d4c7a1f9e3b6
Create Date: 2026-07-16 12:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c5e8f2a91d47'
down_revision: Union[str, None] = 'd4c7a1f9e3b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── influencers: platform discriminator ────────────────────────────────
    op.add_column(
        'influencers',
        sa.Column('platform', sa.String(length=16), server_default='instagram', nullable=False),
    )
    op.add_column(
        'influencers',
        sa.Column('platform_user_id', sa.String(length=64), nullable=True),
    )
    op.create_index(op.f('ix_influencers_platform'), 'influencers', ['platform'], unique=False)
    # A handle is only unique per platform -- @mkbhd can exist on both.
    op.drop_constraint('influencers_handle_key', 'influencers', type_='unique')
    op.create_unique_constraint(
        'uq_influencers_platform_handle', 'influencers', ['platform', 'handle']
    )

    # ── posts: title + platform_metadata ────────────────────────────────────
    op.add_column('posts', sa.Column('title', sa.Text(), nullable=True))
    op.add_column(
        'posts',
        sa.Column('platform_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # ── profile_snapshots: YouTube channel-level extras ─────────────────────
    op.add_column('profile_snapshots', sa.Column('total_views', sa.BigInteger(), nullable=True))
    op.add_column(
        'profile_snapshots',
        sa.Column('subscribers_hidden', sa.Boolean(), server_default='false', nullable=False),
    )
    op.add_column(
        'profile_snapshots',
        sa.Column('platform_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # ── post_metrics_snapshots: likes/comments/reposts become nullable ─────
    # NULL = "not publicly available on this platform" (YouTube hides likes
    # when the creator opts out, has no public share count at all, and
    # omits commentCount when comments are disabled). Existing Instagram
    # rows keep their real values; only new YouTube writes use NULL.
    op.alter_column('post_metrics_snapshots', 'likes', existing_type=sa.Integer(), nullable=True)
    op.alter_column('post_metrics_snapshots', 'comments', existing_type=sa.Integer(), nullable=True)
    op.alter_column(
        'post_metrics_snapshots', 'reposts', existing_type=sa.BigInteger(), nullable=True
    )

    # ── comments: widen IDs, add author_external_id ─────────────────────────
    op.alter_column(
        'comments', 'comment_id', existing_type=sa.String(length=64), type_=sa.String(length=128)
    )
    op.alter_column(
        'comments', 'parent_comment_id',
        existing_type=sa.String(length=64), type_=sa.String(length=128),
    )
    op.add_column('comments', sa.Column('author_external_id', sa.String(length=64), nullable=True))

    # ── youtube_api_keys: new pool table, mirrors instagram_accounts ───────
    op.create_table(
        'youtube_api_keys',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('api_key_encrypted', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('quota_used_today', sa.Integer(), nullable=False),
        sa.Column('quota_reset_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_failure_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_count', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('label'),
    )
    op.create_index(op.f('ix_youtube_api_keys_status'), 'youtube_api_keys', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_youtube_api_keys_status'), table_name='youtube_api_keys')
    op.drop_table('youtube_api_keys')

    op.drop_column('comments', 'author_external_id')
    op.alter_column(
        'comments', 'parent_comment_id',
        existing_type=sa.String(length=128), type_=sa.String(length=64),
    )
    op.alter_column(
        'comments', 'comment_id', existing_type=sa.String(length=128), type_=sa.String(length=64)
    )

    op.alter_column(
        'post_metrics_snapshots', 'reposts', existing_type=sa.BigInteger(), nullable=False
    )
    op.alter_column('post_metrics_snapshots', 'comments', existing_type=sa.Integer(), nullable=False)
    op.alter_column('post_metrics_snapshots', 'likes', existing_type=sa.Integer(), nullable=False)

    op.drop_column('profile_snapshots', 'platform_metadata')
    op.drop_column('profile_snapshots', 'subscribers_hidden')
    op.drop_column('profile_snapshots', 'total_views')

    op.drop_column('posts', 'platform_metadata')
    op.drop_column('posts', 'title')

    op.drop_constraint('uq_influencers_platform_handle', 'influencers', type_='unique')
    op.create_unique_constraint('influencers_handle_key', 'influencers', ['handle'])
    op.drop_index(op.f('ix_influencers_platform'), table_name='influencers')
    op.drop_column('influencers', 'platform_user_id')
    op.drop_column('influencers', 'platform')
