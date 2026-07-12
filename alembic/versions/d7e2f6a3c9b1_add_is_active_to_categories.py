"""add_is_active_to_categories

Revision ID: d7e2f6a3c9b1
Revises: c5a1e9f4b8d3
Create Date: 2026-07-12 09:55:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e2f6a3c9b1'
down_revision: Union[str, None] = 'c5a1e9f4b8d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'categories',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column('categories', 'is_active')
