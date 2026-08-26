"""Add habit_logs table, one row per habit per calendar day, so the 7-day
tick grid can show real completion history instead of just the running
streak counter.

Revision ID: 0013_habit_logs
Revises: 0012_meeting_visible_on_events
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_habit_logs"
down_revision: Union[str, None] = "0012_meeting_visible_on_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "habit_logs" in inspector.get_table_names():
        return
    op.create_table(
        "habit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "habit_id",
            sa.Integer(),
            sa.ForeignKey("habits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("habit_id", "log_date", name="uq_habit_log_date"),
    )
    op.create_index("ix_habit_logs_habit_id", "habit_logs", ["habit_id"])
    op.create_index("ix_habit_logs_log_date", "habit_logs", ["log_date"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "habit_logs" not in inspector.get_table_names():
        return
    op.drop_index("ix_habit_logs_log_date", table_name="habit_logs")
    op.drop_index("ix_habit_logs_habit_id", table_name="habit_logs")
    op.drop_table("habit_logs")
