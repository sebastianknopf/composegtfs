"""Add group_permissions table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_permissions",
        sa.Column(
            "group_id",
            UUID(as_uuid=True),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("permission", sa.String(64), primary_key=True, nullable=False),
    )
    op.create_index("ix_group_permissions_group_id", "group_permissions", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_group_permissions_group_id", table_name="group_permissions")
    op.drop_table("group_permissions")
