"""Add route_band_stops table

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-07
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "route_band_stops",
        # Surrogate PK — allows the same stop to appear multiple times in a band
        sa.Column("id",         PG_UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("route_id",   sa.String(255),   nullable=False),
        sa.Column("direction",  sa.SmallInteger(), nullable=False),
        sa.Column("stop_id",    sa.String(255),   nullable=False),
        sa.Column("sort_order", sa.Integer(),      nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id", name="pk_route_band_stops"),
        # Cascade when the parent version is deleted
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
            name="fk_route_band_stops_version",
            ondelete="CASCADE",
        ),
        # Cascade when the referenced route is deleted
        sa.ForeignKeyConstraint(
            ["version_id", "route_id"],
            ["routes.version_id", "routes.route_id"],
            name="fk_route_band_stops_route",
            ondelete="CASCADE",
        ),
        # Cascade when the referenced stop is deleted
        sa.ForeignKeyConstraint(
            ["version_id", "stop_id"],
            ["stops.version_id", "stops.stop_id"],
            name="fk_route_band_stops_stop",
            ondelete="CASCADE",
        ),
        # No two entries may share the same position within a band
        sa.UniqueConstraint(
            "version_id", "route_id", "direction", "sort_order",
            name="uq_route_band_stops_position",
        ),
    )
    op.create_index(
        "ix_route_band_stops_lookup",
        "route_band_stops",
        ["version_id", "route_id", "direction", "sort_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_route_band_stops_lookup", table_name="route_band_stops")
    op.drop_table("route_band_stops")
