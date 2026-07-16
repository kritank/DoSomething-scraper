"""add_creators_table

Revision ID: a3f7d92c4e18
Revises: c5e8f2a91d47
Create Date: 2026-07-16 21:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f7d92c4e18'
down_revision: Union[str, None] = 'c5e8f2a91d47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'creators',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.add_column('influencers', sa.Column('creator_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_influencers_creator_id'), 'influencers', ['creator_id'], unique=False)
    op.create_foreign_key(
        'fk_influencers_creator_id_creators',
        'influencers', 'creators',
        ['creator_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_influencers_creator_id_creators', 'influencers', type_='foreignkey')
    op.drop_index(op.f('ix_influencers_creator_id'), table_name='influencers')
    op.drop_column('influencers', 'creator_id')
    op.drop_table('creators')
