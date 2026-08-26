"""Add password_reset_tokens table for the forgot/reset password flow.

Revision ID: 0005_password_reset_tokens
Revises: 0004_skill_category
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_password_reset_tokens"
down_revision: Union[str, None] = "0004_skill_category"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "password_reset_tokens" not in tables:
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
        op.create_index("ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True)
        op.create_index("ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"])


def downgrade() -> None:
    if "password_reset_tokens" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("password_reset_tokens")
