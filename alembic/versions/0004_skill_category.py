"""Add category column to skills so entries can be Skill or Current Learning.

Revision ID: 0004_skill_category
Revises: 0003_allowed_emails
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_skill_category"
down_revision: Union[str, None] = "0003_allowed_emails"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {col["name"] for col in sa.inspect(op.get_bind()).get_columns("skills")}
    if "category" not in columns:
        op.add_column("skills", sa.Column("category", sa.String(length=20), nullable=False, server_default="skill"))
        skills = sa.table("skills", sa.column("id", sa.Integer), sa.column("progress", sa.Integer), sa.column("category", sa.String))
        # Backfill: lower-progress seeded skills read more naturally as "Current Learning".
        op.execute(skills.update().where(skills.c.progress < 50).values(category="learning"))
        with op.batch_alter_table("skills") as batch_op:
            batch_op.alter_column("category", server_default=None)


def downgrade() -> None:
    columns = {col["name"] for col in sa.inspect(op.get_bind()).get_columns("skills")}
    if "category" in columns:
        with op.batch_alter_table("skills") as batch_op:
            batch_op.drop_column("category")
