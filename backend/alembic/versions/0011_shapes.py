"""Add shapes table and trip shape_id column

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-10
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shapes",
        sa.Column("version_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("shape_id", sa.String(255), nullable=False),
        sa.Column("shape_name", sa.String(255), nullable=True),
        sa.Column("shape_polyline", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("version_id", "shape_id", name="pk_shapes"),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
            name="fk_shapes_version",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_shapes_version_name", "shapes", ["version_id", "shape_name"])

    op.add_column("trips", sa.Column("shape_id", sa.String(255), nullable=True))
    op.create_index("ix_trips_version_shape", "trips", ["version_id", "shape_id"])


def downgrade() -> None:
    op.drop_index("ix_trips_version_shape", table_name="trips")
    op.drop_column("trips", "shape_id")

    op.drop_index("ix_shapes_version_name", table_name="shapes")
    op.drop_table("shapes")
