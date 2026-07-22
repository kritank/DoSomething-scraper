"""add comment_sync_cursor to posts

Revision ID: a7f21c9d4e5b
Revises: d6e9f4b2c8a3
Create Date: 2026-07-22 13:03:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7f21c9d4e5b'
down_revision: Union[str, None] = 'd6e9f4b2c8a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'posts',
        sa.Column('comment_sync_cursor', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('posts', 'comment_sync_cursor')
