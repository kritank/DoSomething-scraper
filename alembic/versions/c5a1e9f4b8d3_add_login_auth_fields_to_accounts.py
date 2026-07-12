"""add_login_auth_fields_to_accounts

Revision ID: c5a1e9f4b8d3
Revises: b3f0d8e2a1c7
Create Date: 2026-07-12 09:40:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5a1e9f4b8d3'
down_revision: Union[str, None] = 'b3f0d8e2a1c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'instagram_accounts',
        sa.Column('auth_method', sa.String(16), nullable=False, server_default='cookies'),
    )
    op.add_column(
        'instagram_accounts',
        sa.Column('password_encrypted', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('instagram_accounts', 'password_encrypted')
    op.drop_column('instagram_accounts', 'auth_method')
