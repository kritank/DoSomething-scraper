"""add_scraper_account_to_scrape_jobs

Revision ID: b8e21f6a5c93
Revises: a3f7d92c4e18
Create Date: 2026-07-16 22:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8e21f6a5c93'
down_revision: Union[str, None] = 'a3f7d92c4e18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('scrape_jobs', sa.Column('instagram_account_id', sa.UUID(), nullable=True))
    op.add_column('scrape_jobs', sa.Column('youtube_api_key_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_scrape_jobs_instagram_account_id'), 'scrape_jobs', ['instagram_account_id'], unique=False)
    op.create_index(op.f('ix_scrape_jobs_youtube_api_key_id'), 'scrape_jobs', ['youtube_api_key_id'], unique=False)
    op.create_foreign_key(
        'fk_scrape_jobs_instagram_account_id_instagram_accounts',
        'scrape_jobs', 'instagram_accounts',
        ['instagram_account_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_scrape_jobs_youtube_api_key_id_youtube_api_keys',
        'scrape_jobs', 'youtube_api_keys',
        ['youtube_api_key_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_scrape_jobs_youtube_api_key_id_youtube_api_keys', 'scrape_jobs', type_='foreignkey')
    op.drop_constraint('fk_scrape_jobs_instagram_account_id_instagram_accounts', 'scrape_jobs', type_='foreignkey')
    op.drop_index(op.f('ix_scrape_jobs_youtube_api_key_id'), table_name='scrape_jobs')
    op.drop_index(op.f('ix_scrape_jobs_instagram_account_id'), table_name='scrape_jobs')
    op.drop_column('scrape_jobs', 'youtube_api_key_id')
    op.drop_column('scrape_jobs', 'instagram_account_id')
