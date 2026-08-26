"""Add tasks, subtasks and task_streaks tables for Smart Task Management.

Revision ID: 0010_tasks
Revises: 0009_daily_quests
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_tasks"
down_revision: Union[str, None] = "0009_daily_quests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "tasks" not in tables:
        op.create_table(
            "tasks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(length=150), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("category", sa.String(length=20), nullable=False, server_default="personal"),
            sa.Column("priority", sa.String(length=10), nullable=False, server_default="medium"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="todo"),
            sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("progress_percentage", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("xp_awarded", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_tasks_user_id", "tasks", ["user_id"])
        op.create_index("ix_tasks_status", "tasks", ["status"])

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "subtasks" not in tables:
        op.create_table(
            "subtasks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(length=100), nullable=False),
            sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_subtasks_task_id", "subtasks", ["task_id"])

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "task_streaks" not in tables:
        op.create_table(
            "task_streaks",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("current_streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("longest_streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_completed_date", sa.Date(), nullable=True),
        )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "task_streaks" in tables:
        op.drop_table("task_streaks")
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "subtasks" in tables:
        op.drop_table("subtasks")
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "tasks" in tables:
        op.drop_table("tasks")
