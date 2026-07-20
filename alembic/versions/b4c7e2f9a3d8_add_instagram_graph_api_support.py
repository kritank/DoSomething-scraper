"""add_instagram_graph_api_support

Revision ID: b4c7e2f9a3d8
Revises: a785e9a1b792
Create Date: 2026-07-20 09:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4c7e2f9a3d8'
down_revision: Union[str, None] = 'a785e9a1b792'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('instagram_api_tokens',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=False),
    sa.Column('access_token_encrypted', sa.Text(), nullable=False),
    sa.Column('ig_user_id', sa.String(length=64), nullable=False),
    sa.Column('app_id', sa.String(length=64), nullable=False),
    sa.Column('app_secret_encrypted', sa.Text(), nullable=False),
    sa.Column('auth_flavor', sa.String(length=16), nullable=False),
    sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('calls_today', sa.Integer(), nullable=False),
    sa.Column('cooldown_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('buc_usage_pct', sa.Float(), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_failure_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failure_count', sa.Integer(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('label')
    )
    op.create_index(op.f('ix_instagram_api_tokens_status'), 'instagram_api_tokens', ['status'], unique=False)

    op.add_column('influencers', sa.Column('api_supported', sa.Boolean(), nullable=True))

    op.add_column('posts', sa.Column('media_url', sa.Text(), nullable=True))
    op.add_column('posts', sa.Column('thumbnail_url', sa.Text(), nullable=True))

    op.add_column('scrape_jobs', sa.Column('job_type', sa.String(length=16), nullable=False, server_default='scrape'))
    op.add_column('scrape_jobs', sa.Column('instagram_api_token_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_scrape_jobs_instagram_api_token_id_instagram_api_tokens',
        'scrape_jobs', 'instagram_api_tokens',
        ['instagram_api_token_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index(
        op.f('ix_scrape_jobs_instagram_api_token_id'), 'scrape_jobs', ['instagram_api_token_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_scrape_jobs_instagram_api_token_id'), table_name='scrape_jobs')
    op.drop_constraint(
        'fk_scrape_jobs_instagram_api_token_id_instagram_api_tokens', 'scrape_jobs', type_='foreignkey'
    )
    op.drop_column('scrape_jobs', 'instagram_api_token_id')
    op.drop_column('scrape_jobs', 'job_type')

    op.drop_column('posts', 'thumbnail_url')
    op.drop_column('posts', 'media_url')

    op.drop_column('influencers', 'api_supported')

    op.drop_index(op.f('ix_instagram_api_tokens_status'), table_name='instagram_api_tokens')
    op.drop_table('instagram_api_tokens')
