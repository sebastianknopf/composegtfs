"""Add headsigns table and FK constraints for trips / stop_times

Creates the headsigns table (UUID PK, scoped to a version) and wires up
referential integrity from the two pre-existing placeholder columns:

  trips.trip_headsign_id      → headsigns.id  (ON DELETE SET NULL)
  stop_times.stop_headsign_id → headsigns.id  (ON DELETE SET NULL)

Both placeholder columns are first nullified (they were always NULL in
practice — no headsigns existed before this migration) and then retyped
from varchar(255) to UUID so the FK constraints can be established.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Create headsigns table
    # ------------------------------------------------------------------
    op.create_table(
        "headsigns",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("number", sa.String(64), nullable=True),
        sa.Column("destination", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_headsigns"),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
            name="fk_headsigns_version_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("version_id", "name", name="uq_headsigns_version_name"),
    )
    op.create_index("ix_headsigns_version_id", "headsigns", ["version_id"])

    # ------------------------------------------------------------------
    # 2. Retype placeholder columns to UUID
    #    These columns were always NULL (headsigns did not exist before),
    #    so we can safely NULL them first to avoid any cast failures.
    # ------------------------------------------------------------------
    op.execute("UPDATE trips SET trip_headsign_id = NULL")
    op.execute("UPDATE stop_times SET stop_headsign_id = NULL")

    op.alter_column(
        "trips",
        "trip_headsign_id",
        existing_type=sa.String(255),
        type_=UUID(as_uuid=True),
        postgresql_using="NULL::uuid",
        nullable=True,
    )
    op.alter_column(
        "stop_times",
        "stop_headsign_id",
        existing_type=sa.String(255),
        type_=UUID(as_uuid=True),
        postgresql_using="NULL::uuid",
        nullable=True,
    )

    # ------------------------------------------------------------------
    # 3. Add FK constraints with ON DELETE SET NULL
    # ------------------------------------------------------------------
    op.create_foreign_key(
        "fk_trips_headsign_id",
        "trips",
        "headsigns",
        ["trip_headsign_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_stop_times_headsign_id",
        "stop_times",
        "headsigns",
        ["stop_headsign_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_stop_times_headsign_id", "stop_times", type_="foreignkey")
    op.drop_constraint("fk_trips_headsign_id", "trips", type_="foreignkey")

    op.alter_column(
        "stop_times",
        "stop_headsign_id",
        existing_type=UUID(as_uuid=True),
        type_=sa.String(255),
        postgresql_using="stop_headsign_id::text",
        nullable=True,
    )
    op.alter_column(
        "trips",
        "trip_headsign_id",
        existing_type=UUID(as_uuid=True),
        type_=sa.String(255),
        postgresql_using="trip_headsign_id::text",
        nullable=True,
    )

    op.drop_index("ix_headsigns_version_id", table_name="headsigns")
    op.drop_table("headsigns")
