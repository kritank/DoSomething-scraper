"""add_scrape_scoping_and_perf_indexes

Revision ID: 970d3851dd92
Revises: f3a8c1d2e9b4
Create Date: 2026-07-08 00:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '970d3851dd92'
down_revision: Union[str, None] = 'f3a8c1d2e9b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('influencers', sa.Column('scrape_posts_since', sa.Date(), nullable=True))
    op.add_column(
        'influencers',
        sa.Column('backfill_completed', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('influencers', sa.Column('backfill_cursor', sa.String(length=128), nullable=True))

    # Existing influencers already have their history backfilled -- only
    # influencers with zero posts saved so far should start a fresh
    # (resumable) backfill under the new column.
    op.execute(
        "UPDATE influencers SET backfill_completed = true "
        "WHERE id IN (SELECT DISTINCT influencer_id FROM posts)"
    )

    op.create_index(
        'ix_posts_influencer_id_posted_at', 'posts', ['influencer_id', 'posted_at'], unique=False
    )
    op.create_index(op.f('ix_comments_post_id'), 'comments', ['post_id'], unique=False)
    op.create_index(
        op.f('ix_post_metrics_snapshots_post_id'), 'post_metrics_snapshots', ['post_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_post_metrics_snapshots_post_id'), table_name='post_metrics_snapshots')
    op.drop_index(op.f('ix_comments_post_id'), table_name='comments')
    op.drop_index('ix_posts_influencer_id_posted_at', table_name='posts')
    op.drop_column('influencers', 'backfill_cursor')
    op.drop_column('influencers', 'backfill_completed')
    op.drop_column('influencers', 'scrape_posts_since')
