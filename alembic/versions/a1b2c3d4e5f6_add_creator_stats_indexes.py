"""add_creator_stats_indexes

Revision ID: a1b2c3d4e5f6
Revises: d7f3b1e4a682
Create Date: 2026-07-17 00:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'd7f3b1e4a682'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backs the creator-stats growth/engagement queries (app/analytics/creator_stats.py),
    # which all filter by influencer/post and order by scraped_at/posted_at.
    op.create_index(
        'ix_profile_snapshots_influencer_scraped',
        'profile_snapshots',
        ['influencer_id', 'scraped_at'],
    )
    op.create_index(
        'ix_post_metrics_snapshots_post_scraped',
        'post_metrics_snapshots',
        ['post_id', 'scraped_at'],
    )
    # posts(influencer_id, posted_at) is already covered by
    # ix_posts_influencer_id_posted_at (see app/models/post.py Index()) --
    # not duplicated here.


def downgrade() -> None:
    op.drop_index('ix_post_metrics_snapshots_post_scraped', table_name='post_metrics_snapshots')
    op.drop_index('ix_profile_snapshots_influencer_scraped', table_name='profile_snapshots')
