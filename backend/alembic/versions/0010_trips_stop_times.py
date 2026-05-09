"""Add trips and stop_times tables

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-08
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # trips
    # ------------------------------------------------------------------
    op.create_table(
        "trips",
        sa.Column("version_id",            PG_UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id",               sa.String(255),        nullable=False),
        sa.Column("route_id",              sa.String(255),        nullable=False),
        # service_id: no DB-level FK (composite SET NULL would also null version_id)
        sa.Column("service_id",            sa.String(255),        nullable=True),
        sa.Column("direction_id",          sa.SmallInteger(),     nullable=True),
        sa.Column("trip_short_name",       sa.String(255),        nullable=True),
        sa.Column("trip_headsign_id",      sa.String(255),        nullable=True),
        sa.Column("block_id",              sa.String(255),        nullable=True),
        sa.Column("wheelchair_accessible", sa.SmallInteger(),     nullable=True),
        sa.Column("bikes_allowed",         sa.SmallInteger(),     nullable=True),
        sa.Column("cars_allowed",          sa.SmallInteger(),     nullable=True),
        sa.Column("geo_pattern_hash",      sa.String(64),         nullable=True),
        sa.Column("schedule_pattern_hash", sa.String(64),         nullable=True),
        sa.PrimaryKeyConstraint("version_id", "trip_id", name="pk_trips"),
        # Cascade when the parent version is deleted
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
            name="fk_trips_version",
            ondelete="CASCADE",
        ),
        # Cascade when the referenced route is deleted
        sa.ForeignKeyConstraint(
            ["version_id", "route_id"],
            ["routes.version_id", "routes.route_id"],
            name="fk_trips_route",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_trips_version_route", "trips", ["version_id", "route_id"])
    op.create_index("ix_trips_version_service", "trips", ["version_id", "service_id"])

    # ------------------------------------------------------------------
    # stop_times
    # ------------------------------------------------------------------
    op.create_table(
        "stop_times",
        sa.Column("version_id",           PG_UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id",              sa.String(255),        nullable=False),
        sa.Column("route_band_stop_id",   PG_UUID(as_uuid=True), nullable=False),
        # Times stored as GTFS "H+:MM:SS" strings (may exceed 24 h)
        sa.Column("arrival_time",         sa.String(8),          nullable=True),
        sa.Column("departure_time",       sa.String(8),          nullable=True),
        sa.Column("stop_headsign_id",     sa.String(255),        nullable=True),
        sa.Column("pickup_type",          sa.SmallInteger(),     nullable=True),
        sa.Column("drop_off_type",        sa.SmallInteger(),     nullable=True),
        sa.Column("continuous_pickup",    sa.SmallInteger(),     nullable=True),
        sa.Column("continuous_drop_off",  sa.SmallInteger(),     nullable=True),
        sa.Column("shape_dist_traveled",  sa.Float(),            nullable=True),
        sa.Column("timepoint",            sa.SmallInteger(),     nullable=True),
        sa.PrimaryKeyConstraint("version_id", "trip_id", "route_band_stop_id", name="pk_stop_times"),
        # Cascade when the parent version is deleted
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
            name="fk_stop_times_version",
            ondelete="CASCADE",
        ),
        # Cascade when the parent trip is deleted
        sa.ForeignKeyConstraint(
            ["version_id", "trip_id"],
            ["trips.version_id", "trips.trip_id"],
            name="fk_stop_times_trip",
            ondelete="CASCADE",
        ),
        # Cascade when the route_band_stop entry is removed from the band
        sa.ForeignKeyConstraint(
            ["route_band_stop_id"],
            ["route_band_stops.id"],
            name="fk_stop_times_route_band_stop",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_stop_times_trip", "stop_times", ["version_id", "trip_id"])
    op.create_index("ix_stop_times_band_stop", "stop_times", ["route_band_stop_id"])


def downgrade() -> None:
    op.drop_index("ix_stop_times_band_stop", table_name="stop_times")
    op.drop_index("ix_stop_times_trip",      table_name="stop_times")
    op.drop_table("stop_times")

    op.drop_index("ix_trips_version_service", table_name="trips")
    op.drop_index("ix_trips_version_route",   table_name="trips")
    op.drop_table("trips")
