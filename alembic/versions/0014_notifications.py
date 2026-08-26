"""Add notifications table.

The Notification model has existed in models.py for a while (welcome message,
answer/like/quest-claim notifications), but it was never given its own
migration — it only ever got created via Base.metadata.create_all, which dev/
test use but production (migration-driven) does not. This backfills that gap
and is additive-only for existing deployments.

Revision ID: 0014_notifications
Revises: 0013_habit_logs
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_notifications"
down_revision: Union[str, None] = "0013_habit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "notifications" in inspector.get_table_names():
        return
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message", sa.String(length=400), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False, server_default="info"),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "notifications" not in inspector.get_table_names():
        return
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
