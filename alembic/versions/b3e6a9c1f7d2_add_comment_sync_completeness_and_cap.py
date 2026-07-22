"""add comment sync completeness tracking and per-influencer cap

Revision ID: b3e6a9c1f7d2
Revises: a7f21c9d4e5b
Create Date: 2026-07-22 15:41:32.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3e6a9c1f7d2'
down_revision: Union[str, None] = 'a7f21c9d4e5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'posts',
        sa.Column('comments_synced_count', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'influencers',
        sa.Column('max_comments_per_post', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('influencers', 'max_comments_per_post')
    op.drop_column('posts', 'comments_synced_count')
