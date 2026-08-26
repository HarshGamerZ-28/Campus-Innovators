"""Add opportunities table for the Opportunity Board.

Revision ID: 0011_opportunities
Revises: 0010_tasks
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_opportunities"
down_revision: Union[str, None] = "0010_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "opportunities" not in tables:
        op.create_table(
            "opportunities",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(length=150), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("type", sa.String(length=20), nullable=False, server_default="other"),
            sa.Column("organization", sa.String(length=100), nullable=False),
            sa.Column("external_link", sa.String(length=500), nullable=False),
            sa.Column("deadline", sa.Date(), nullable=True),
            sa.Column("location", sa.String(length=150), nullable=True),
            sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_opportunities_submitted_by", "opportunities", ["submitted_by"])
        op.create_index("ix_opportunities_status", "opportunities", ["status"])
        op.create_index("ix_opportunities_created_at", "opportunities", ["created_at"])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "opportunities" in tables:
        op.drop_table("opportunities")
