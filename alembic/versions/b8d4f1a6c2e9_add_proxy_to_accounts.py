"""add_proxy_to_accounts

Revision ID: b8d4f1a6c2e9
Revises: a4d8f2c6e9b3
Create Date: 2026-07-15 00:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d4f1a6c2e9'
down_revision: Union[str, None] = 'a4d8f2c6e9b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'instagram_accounts',
        sa.Column('proxy_encrypted', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('instagram_accounts', 'proxy_encrypted')
