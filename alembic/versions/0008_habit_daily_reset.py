"""Add last_completed_on to habits, used to lazily reset them each day and
gate habit XP to once per day.

Revision ID: 0008_habit_daily_reset
Revises: 0007_meetings
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_habit_daily_reset"
down_revision: Union[str, None] = "0007_meetings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {col["name"] for col in sa.inspect(op.get_bind()).get_columns("habits")}
    if "last_completed_on" not in columns:
        op.add_column("habits", sa.Column("last_completed_on", sa.Date(), nullable=True))


def downgrade() -> None:
    columns = {col["name"] for col in sa.inspect(op.get_bind()).get_columns("habits")}
    if "last_completed_on" in columns:
        op.drop_column("habits", "last_completed_on")
