"""add profile_pic_url to influencers

Revision ID: 2f485d66af55
Revises: a1b2c3d4e5f6
Create Date: 2026-07-17 23:09:20.663568+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f485d66af55'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('influencers', sa.Column('profile_pic_url', sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column('influencers', 'profile_pic_url')
