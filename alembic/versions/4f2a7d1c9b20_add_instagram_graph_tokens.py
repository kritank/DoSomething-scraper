"""add_instagram_graph_tokens

Revision ID: 4f2a7d1c9b20
Revises: a3f7d92c4e18
Create Date: 2026-07-20 00:00:00.000000+00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4f2a7d1c9b20"
down_revision: Union[str, None] = "a3f7d92c4e18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instagram_graph_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("label"),
    )
    op.create_index(op.f("ix_instagram_graph_tokens_status"), "instagram_graph_tokens", ["status"], unique=False)
    op.create_index(op.f("ix_instagram_graph_tokens_cooldown_until"), "instagram_graph_tokens", ["cooldown_until"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_instagram_graph_tokens_cooldown_until"), table_name="instagram_graph_tokens")
    op.drop_index(op.f("ix_instagram_graph_tokens_status"), table_name="instagram_graph_tokens")
    op.drop_table("instagram_graph_tokens")
