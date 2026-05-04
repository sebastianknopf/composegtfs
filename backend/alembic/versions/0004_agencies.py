"""Add agencies table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agencies",
        sa.Column("version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("agency_id", sa.String(255), nullable=False),
        sa.Column("agency_name", sa.String(255), nullable=False),
        sa.Column("agency_url", sa.String(2048), nullable=False),
        sa.Column("agency_timezone", sa.String(64), nullable=False),
        sa.Column("agency_lang", sa.String(35), nullable=True),
        sa.Column("agency_phone", sa.String(64), nullable=True),
        sa.Column("agency_fare_url", sa.String(2048), nullable=True),
        sa.Column("agency_email", sa.String(254), nullable=True),
        sa.Column("cemv_support", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("version_id", "agency_id", name="pk_agencies"),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
            name="fk_agencies_version_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_agencies_version_id", "agencies", ["version_id"])


def downgrade() -> None:
    op.drop_index("ix_agencies_version_id", table_name="agencies")
    op.drop_table("agencies")
