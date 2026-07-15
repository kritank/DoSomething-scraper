"""widen_post_metrics_snapshot_counts

Revision ID: d4c7a1f9e3b6
Revises: b8d4f1a6c2e9
Create Date: 2026-07-15 08:36:29.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4c7a1f9e3b6'
down_revision: Union[str, None] = 'b8d4f1a6c2e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A viral reel's play/reshare count routinely exceeds Integer's
    # ~2.1B range.
    op.alter_column(
        'post_metrics_snapshots', 'views',
        existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=True,
    )
    op.alter_column(
        'post_metrics_snapshots', 'reposts',
        existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'post_metrics_snapshots', 'reposts',
        existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=False,
    )
    op.alter_column(
        'post_metrics_snapshots', 'views',
        existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=True,
    )
