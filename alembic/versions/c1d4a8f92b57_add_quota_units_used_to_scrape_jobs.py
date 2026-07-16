"""add_quota_units_used_to_scrape_jobs

Revision ID: c1d4a8f92b57
Revises: b8e21f6a5c93
Create Date: 2026-07-16 23:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d4a8f92b57'
down_revision: Union[str, None] = 'b8e21f6a5c93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('scrape_jobs', sa.Column('quota_units_used', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('scrape_jobs', 'quota_units_used')
