"""add_last_heartbeat_at_to_scrape_jobs

Revision ID: f1a9c3e7b2d6
Revises: e4b8a2c7f1d5
Create Date: 2026-07-13 08:30:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a9c3e7b2d6'
down_revision: Union[str, None] = 'e4b8a2c7f1d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'scrape_jobs',
        sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Partial index scoped to the reap_stale_running() query pattern
    # (status='running' is always a small, short-lived row count, but the
    # index keeps that scan cheap regardless of total table size).
    op.create_index(
        'ix_scrape_jobs_running_heartbeat',
        'scrape_jobs',
        ['last_heartbeat_at'],
        unique=False,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index('ix_scrape_jobs_running_heartbeat', table_name='scrape_jobs')
    op.drop_column('scrape_jobs', 'last_heartbeat_at')
