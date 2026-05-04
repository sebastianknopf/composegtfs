"""Initial schema: users, groups, user_groups, app_settings

Revision ID: 0001
Revises:
Create Date: 2026-05-01
"""
from __future__ import annotations

import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("email", sa.String(254), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(256), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_superuser", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "groups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(64), unique=True, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_groups_name", "groups", ["name"])

    op.create_table(
        "user_groups",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_groups")
    op.drop_table("users")
    op.drop_table("groups")
    op.drop_table("app_settings")
