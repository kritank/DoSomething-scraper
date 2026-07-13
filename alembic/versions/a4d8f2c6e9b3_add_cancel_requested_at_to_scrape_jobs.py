"""add_cancel_requested_at_to_scrape_jobs

Revision ID: a4d8f2c6e9b3
Revises: f1a9c3e7b2d6
Create Date: 2026-07-13 14:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4d8f2c6e9b3'
down_revision: Union[str, None] = 'f1a9c3e7b2d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'scrape_jobs',
        sa.Column('cancel_requested_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('scrape_jobs', 'cancel_requested_at')
