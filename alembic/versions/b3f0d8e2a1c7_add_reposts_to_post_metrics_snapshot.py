"""add_reposts_to_post_metrics_snapshot

Revision ID: b3f0d8e2a1c7
Revises: 970d3851dd92
Create Date: 2026-07-12 09:15:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f0d8e2a1c7'
down_revision: Union[str, None] = '970d3851dd92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'post_metrics_snapshots',
        sa.Column('reposts', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('post_metrics_snapshots', 'reposts')
