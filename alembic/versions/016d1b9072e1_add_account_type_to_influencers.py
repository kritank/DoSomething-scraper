"""add account_type to influencers

Revision ID: 016d1b9072e1
Revises: 525b85671309
Create Date: 2026-07-19 03:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '016d1b9072e1'
down_revision: Union[str, None] = '525b85671309'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'influencers',
        sa.Column('account_type', sa.String(length=16), server_default='individual', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('influencers', 'account_type')
