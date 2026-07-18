"""add post_outlier_metrics table

Revision ID: 29826e6edfb0
Revises: 2f485d66af55
Create Date: 2026-07-19 00:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '29826e6edfb0'
down_revision: Union[str, None] = '2f485d66af55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'post_outlier_metrics',
        sa.Column('post_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('outlier_score', sa.Float(), nullable=True),
        sa.Column('baseline_multiple', sa.Float(), nullable=True),
        sa.Column('vph_current', sa.Float(), nullable=True),
        sa.Column('vph_lifetime', sa.Float(), nullable=True),
        sa.Column('engagement_ratio', sa.Float(), nullable=True),
        sa.Column('baseline_median', sa.Float(), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('post_id'),
    )
    op.create_index(
        'ix_post_outlier_metrics_score',
        'post_outlier_metrics',
        ['outlier_score'],
        unique=False,
        postgresql_where=sa.text('outlier_score IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index(
        'ix_post_outlier_metrics_score',
        table_name='post_outlier_metrics',
        postgresql_where=sa.text('outlier_score IS NOT NULL'),
    )
    op.drop_table('post_outlier_metrics')
