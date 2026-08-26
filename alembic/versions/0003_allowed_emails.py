"""Add allowed_emails table for admin-managed registration allowlist.

Revision ID: 0003_allowed_emails
Revises: 0002_production_profiles_auth
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_allowed_emails"
down_revision: Union[str, None] = "0002_production_profiles_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "allowed_emails" not in tables:
        op.create_table(
            "allowed_emails",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("added_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("note", sa.String(length=255), nullable=True),
            sa.UniqueConstraint("email"),
        )
        op.create_index("ix_allowed_emails_email", "allowed_emails", ["email"], unique=True)
        op.create_index("ix_allowed_emails_added_by_id", "allowed_emails", ["added_by_id"])


def downgrade() -> None:
    if "allowed_emails" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("allowed_emails")
