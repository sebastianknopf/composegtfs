"""Extend shapes table and add shape_intermediate_points

- Add columns description, route_type, is_autoroute_active to shapes
- Create shape_intermediate_points table with FK to shapes (CASCADE)
  and optional FK to stops (CASCADE)

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-15
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extend shapes table
    # ------------------------------------------------------------------
    op.add_column("shapes", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("shapes", sa.Column("route_type", sa.Integer(), nullable=True))
    op.add_column(
        "shapes",
        sa.Column("is_autoroute_active", sa.Boolean(), nullable=False, server_default="false"),
    )

    # ------------------------------------------------------------------
    # New table: shape_intermediate_points
    # Each row is either a free lat/lon point or a reference to a stop.
    # ------------------------------------------------------------------
    op.create_table(
        "shape_intermediate_points",
        sa.Column("id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("shape_id", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        # Free coordinate (used when stop_id IS NULL)
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        # Stop reference (used when stop_id IS NOT NULL; lat/lon are ignored)
        sa.Column("stop_id", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_shape_intermediate_points"),
        # FK → shapes (CASCADE: deleting a shape removes all its intermediate points)
        sa.ForeignKeyConstraint(
            ["version_id", "shape_id"],
            ["shapes.version_id", "shapes.shape_id"],
            name="fk_sip_shape",
            ondelete="CASCADE",
        ),
        # FK → stops (CASCADE: deleting a stop removes all intermediate points that reference it)
        # NULL stop_id rows are unaffected by this constraint.
        sa.ForeignKeyConstraint(
            ["version_id", "stop_id"],
            ["stops.version_id", "stops.stop_id"],
            name="fk_sip_stop",
            ondelete="CASCADE",
        ),
    )

    op.create_index(
        "ix_sip_shape",
        "shape_intermediate_points",
        ["version_id", "shape_id", "sort_order"],
    )
    op.create_index(
        "ix_sip_stop",
        "shape_intermediate_points",
        ["version_id", "stop_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sip_stop", table_name="shape_intermediate_points")
    op.drop_index("ix_sip_shape", table_name="shape_intermediate_points")
    op.drop_table("shape_intermediate_points")

    op.drop_column("shapes", "is_autoroute_active")
    op.drop_column("shapes", "route_type")
    op.drop_column("shapes", "description")
