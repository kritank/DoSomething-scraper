"""add_instagram_api_token_health_columns

Revision ID: c5d8f3a1b7e2
Revises: b4c7e2f9a3d8
Create Date: 2026-07-20 09:30:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5d8f3a1b7e2'
down_revision: Union[str, None] = 'b4c7e2f9a3d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('credential_health_snapshots', sa.Column('buc_usage_pct', sa.Float(), nullable=True))
    op.add_column('credential_health_snapshots', sa.Column('instagram_api_token_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_credential_health_snapshots_ig_api_token_id',
        'credential_health_snapshots', 'instagram_api_tokens',
        ['instagram_api_token_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index(
        op.f('ix_credential_health_snapshots_instagram_api_token_id'),
        'credential_health_snapshots', ['instagram_api_token_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_credential_health_snapshots_instagram_api_token_id'),
        table_name='credential_health_snapshots',
    )
    op.drop_constraint(
        'fk_credential_health_snapshots_ig_api_token_id',
        'credential_health_snapshots', type_='foreignkey',
    )
    op.drop_column('credential_health_snapshots', 'instagram_api_token_id')
    op.drop_column('credential_health_snapshots', 'buc_usage_pct')
