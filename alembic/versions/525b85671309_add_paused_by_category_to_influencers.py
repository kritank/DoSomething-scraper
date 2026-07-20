"""add paused_by_category to influencers

Revision ID: 525b85671309
Revises: 29826e6edfb0
Create Date: 2026-07-19 02:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '525b85671309'
down_revision: Union[str, None] = '29826e6edfb0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'influencers',
        sa.Column('paused_by_category', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('influencers', 'paused_by_category')
