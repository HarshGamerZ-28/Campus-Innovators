"""Add daily_xp_ledger table so XP grants can be capped per user per day.

Revision ID: 0006_daily_xp_ledger
Revises: 0005_password_reset_tokens
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_daily_xp_ledger"
down_revision: Union[str, None] = "0005_password_reset_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "daily_xp_ledger" not in tables:
        op.create_table(
            "daily_xp_ledger",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("xp_date", sa.Date(), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("user_id", "xp_date", name="uq_user_xp_date"),
        )
        op.create_index("ix_daily_xp_ledger_user_id", "daily_xp_ledger", ["user_id"])
        op.create_index("ix_daily_xp_ledger_xp_date", "daily_xp_ledger", ["xp_date"])


def downgrade() -> None:
    if "daily_xp_ledger" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("daily_xp_ledger")
