"""add_instagram_accounts_table

Revision ID: f3a8c1d2e9b4
Revises: a69595866b73
Create Date: 2026-07-04 19:30:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a8c1d2e9b4'
down_revision: Union[str, None] = 'a69595866b73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('instagram_accounts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('username', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('session_cookies_encrypted', sa.Text(), nullable=False),
    sa.Column('session_captured_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('user_agent', sa.String(length=512), nullable=False),
    sa.Column('locale', sa.String(length=16), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_failure_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failure_count', sa.Integer(), nullable=False),
    sa.Column('cooldown_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('locked_by', sa.String(length=128), nullable=True),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_index(op.f('ix_instagram_accounts_status'), 'instagram_accounts', ['status'], unique=False)
    op.create_index(op.f('ix_instagram_accounts_cooldown_until'), 'instagram_accounts', ['cooldown_until'], unique=False)
    op.create_index('ix_instagram_accounts_status_cooldown_until', 'instagram_accounts', ['status', 'cooldown_until'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_instagram_accounts_status_cooldown_until', table_name='instagram_accounts')
    op.drop_index(op.f('ix_instagram_accounts_cooldown_until'), table_name='instagram_accounts')
    op.drop_index(op.f('ix_instagram_accounts_status'), table_name='instagram_accounts')
    op.drop_table('instagram_accounts')
