"""Add versions table

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "versions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_versions_name"),
    )
    op.create_index("ix_versions_name", "versions", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_versions_name", table_name="versions")
    op.drop_table("versions")
