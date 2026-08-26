"""Add is_daily / cycle_index / assigned_on to quests, powering the
7-day repeating daily-quest cycle.

Revision ID: 0009_daily_quests
Revises: 0008_habit_daily_reset
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_daily_quests"
down_revision: Union[str, None] = "0008_habit_daily_reset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {col["name"] for col in sa.inspect(op.get_bind()).get_columns("quests")}
    if "is_daily" not in columns:
        op.add_column("quests", sa.Column("is_daily", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "cycle_index" not in columns:
        op.add_column("quests", sa.Column("cycle_index", sa.Integer(), nullable=True))
    if "assigned_on" not in columns:
        op.add_column("quests", sa.Column("assigned_on", sa.Date(), nullable=True))


def downgrade() -> None:
    columns = {col["name"] for col in sa.inspect(op.get_bind()).get_columns("quests")}
    for name in ("assigned_on", "cycle_index", "is_daily"):
        if name in columns:
            op.drop_column("quests", name)
