"""add_comments_processed_to_scrape_jobs

Revision ID: e4b8a2c7f1d5
Revises: d7e2f6a3c9b1
Create Date: 2026-07-12 10:20:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4b8a2c7f1d5'
down_revision: Union[str, None] = 'd7e2f6a3c9b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'scrape_jobs',
        sa.Column('comments_processed', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('scrape_jobs', 'comments_processed')
