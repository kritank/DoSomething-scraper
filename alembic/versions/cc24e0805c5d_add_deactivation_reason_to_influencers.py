"""add deactivation_reason to influencers

Revision ID: cc24e0805c5d
Revises: 016d1b9072e1
Create Date: 2026-07-19 04:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc24e0805c5d'
down_revision: Union[str, None] = '016d1b9072e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'influencers',
        sa.Column('deactivation_reason', sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('influencers', 'deactivation_reason')
