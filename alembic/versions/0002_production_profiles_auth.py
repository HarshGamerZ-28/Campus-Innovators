"""Add public profiles, avatar ownership, activity graph and refresh sessions.

Revision ID: 0002_production_profiles_auth
Revises: 0001_initial
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_production_profiles_auth"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if "users" in tables:
        cols = _columns("users")
        additions = []
        if "username" not in cols:
            additions.append(sa.Column("username", sa.String(length=40), nullable=True))
        if "avatar_key" not in cols:
            additions.append(sa.Column("avatar_key", sa.String(length=80), nullable=False, server_default="avatar-01"))
        if "hero_avatar_url" not in cols:
            additions.append(sa.Column("hero_avatar_url", sa.String(length=500), nullable=False, server_default="/assets/avatars/avatar-01.webp"))
        if "is_public" not in cols:
            additions.append(sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()))
        if "is_active" not in cols:
            additions.append(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        if "email_verified" not in cols:
            additions.append(sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "last_login_at" not in cols:
            additions.append(sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
        if "updated_at" not in cols:
            additions.append(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        if additions:
            with op.batch_alter_table("users") as batch:
                for column in additions:
                    batch.add_column(column)

        cols = _columns("users")
        if "username" in cols:
            connection = op.get_bind()
            rows = connection.execute(sa.text("SELECT id, email, username FROM users ORDER BY id")).mappings().all()
            used: set[str] = set()
            for row in rows:
                base = (row["username"] or row["email"].split("@", 1)[0]).lower().replace(" ", "")[:26] or f"student{row['id']}"
                candidate = base
                suffix = 1
                while candidate in used:
                    suffix += 1
                    candidate = f"{base[:26]}{suffix}"
                used.add(candidate)
                connection.execute(sa.text("UPDATE users SET username=:username WHERE id=:id"), {"username": candidate, "id": row["id"]})
            existing_indexes = {item["name"] for item in sa.inspect(connection).get_indexes("users")}
            if "ix_users_username" not in existing_indexes:
                op.create_index("ix_users_username", "users", ["username"], unique=True)

    if "posts" in tables and "is_public" not in _columns("posts"):
        with op.batch_alter_table("posts") as batch:
            batch.add_column(sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()))

    if "projects" in tables:
        cols = _columns("projects")
        with op.batch_alter_table("projects") as batch:
            if "github_url" not in cols:
                batch.add_column(sa.Column("github_url", sa.String(length=500), nullable=False, server_default=""))
            if "demo_url" not in cols:
                batch.add_column(sa.Column("demo_url", sa.String(length=500), nullable=False, server_default=""))
            if "is_public" not in cols:
                batch.add_column(sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()))
            if "updated_at" not in cols:
                batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "avatars" not in tables:
        op.create_table(
            "avatars",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("key", sa.String(length=80), nullable=False),
            sa.Column("label", sa.String(length=120), nullable=False),
            sa.Column("image_url", sa.String(length=500), nullable=False),
            sa.Column("hero_image_url", sa.String(length=500), nullable=False),
            sa.Column("reserved_email", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("key"),
        )
        op.create_index("ix_avatars_key", "avatars", ["key"], unique=True)
        op.create_index("ix_avatars_reserved_email", "avatars", ["reserved_email"])

    if "refresh_sessions" not in tables:
        op.create_table(
            "refresh_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("jti", sa.String(length=64), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("replaced_by_jti", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("ip_address", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("jti"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index("ix_refresh_sessions_jti", "refresh_sessions", ["jti"], unique=True)
        op.create_index("ix_refresh_sessions_token_hash", "refresh_sessions", ["token_hash"], unique=True)
        op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
        op.create_index("ix_refresh_sessions_expires_at", "refresh_sessions", ["expires_at"])

    if "activity_days" not in tables:
        op.create_table(
            "activity_days",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("activity_date", sa.Date(), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("user_id", "activity_date", name="uq_user_activity_date"),
        )
        op.create_index("ix_activity_days_user_id", "activity_days", ["user_id"])
        op.create_index("ix_activity_days_activity_date", "activity_days", ["activity_date"])

    if "platform_settings" not in tables:
        op.create_table(
            "platform_settings",
            sa.Column("key", sa.String(length=100), primary_key=True),
            sa.Column("value", sa.Text(), nullable=False, server_default=""),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )


def downgrade() -> None:
    for table in ["platform_settings", "activity_days", "refresh_sessions", "avatars"]:
        if table in sa.inspect(op.get_bind()).get_table_names():
            op.drop_table(table)
