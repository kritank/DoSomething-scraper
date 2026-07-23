"""add_leaderboard_filter_indexes

Revision ID: b7d4f2a8c3e1
Revises: b3e6a9c1f7d2
Create Date: 2026-07-24 00:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7d4f2a8c3e1'
down_revision: Union[str, None] = 'b3e6a9c1f7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backs InfluencerRepo._leaderboard_base_stmt's WHERE/JOIN clauses
    # (used by both GET /influencers/top and GET /creators/{id}) -- neither
    # column had an index despite being filtered/joined on every call.
    op.create_index('ix_influencers_is_active', 'influencers', ['is_active'])
    op.create_index('ix_influencers_category_id', 'influencers', ['category_id'])


def downgrade() -> None:
    op.drop_index('ix_influencers_category_id', table_name='influencers')
    op.drop_index('ix_influencers_is_active', table_name='influencers')
