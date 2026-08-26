"""Add visible_on_events flag to meetings so they can surface on the public Events feed.

Revision ID: 0012_meeting_visible_on_events
Revises: 0011_opportunities
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_meeting_visible_on_events"
down_revision: Union[str, None] = "0011_opportunities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {col["name"] for col in sa.inspect(op.get_bind()).get_columns("meetings")}
    if "visible_on_events" not in columns:
        op.add_column(
            "meetings",
            sa.Column("visible_on_events", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    columns = {col["name"] for col in sa.inspect(op.get_bind()).get_columns("meetings")}
    if "visible_on_events" in columns:
        op.drop_column("meetings", "visible_on_events")
