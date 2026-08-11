"""Add meetings and meeting_attendance tables for the admin Meeting section.

Revision ID: 0007_meetings
Revises: 0006_daily_xp_ledger
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_meetings"
down_revision: Union[str, None] = "0006_daily_xp_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "meetings" not in tables:
        op.create_table(
            "meetings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("location", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_meetings_scheduled_at", "meetings", ["scheduled_at"])
        op.create_index("ix_meetings_created_by_id", "meetings", ["created_by_id"])

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "meeting_attendance" not in tables:
        op.create_table(
            "meeting_attendance",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("meeting_id", sa.Integer(), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("marked_present_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("meeting_id", "user_id", name="uq_meeting_user"),
        )
        op.create_index("ix_meeting_attendance_meeting_id", "meeting_attendance", ["meeting_id"])
        op.create_index("ix_meeting_attendance_user_id", "meeting_attendance", ["user_id"])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "meeting_attendance" in tables:
        op.drop_table("meeting_attendance")
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "meetings" in tables:
        op.drop_table("meetings")
