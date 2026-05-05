"""Add stops table (GTFS stops.txt, scoped to version)

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stops",
        sa.Column("version_id",           UUID(as_uuid=True),    nullable=False),
        sa.Column("stop_id",              sa.String(255),        nullable=False),
        sa.Column("stop_code",            sa.String(255),        nullable=True),
        sa.Column("stop_name",            sa.Text(),             nullable=True),
        sa.Column("tts_stop_name",        sa.Text(),             nullable=True),
        sa.Column("stop_desc",            sa.Text(),             nullable=True),
        sa.Column("stop_lat",             sa.Float(),            nullable=True),
        sa.Column("stop_lon",             sa.Float(),            nullable=True),
        sa.Column("zone_id",              sa.String(255),        nullable=True),
        sa.Column("stop_url",             sa.String(2048),       nullable=True),
        sa.Column("location_type",        sa.SmallInteger(),     nullable=True),
        sa.Column("parent_station",       sa.String(255),        nullable=True),
        sa.Column("stop_timezone",        sa.String(64),         nullable=True),
        sa.Column("wheelchair_boarding",  sa.SmallInteger(),     nullable=True),
        sa.Column("level_id",             sa.String(255),        nullable=True),
        sa.Column("platform_code",        sa.String(255),        nullable=True),
        sa.Column("stop_access",          sa.SmallInteger(),     nullable=True),
        sa.PrimaryKeyConstraint("version_id", "stop_id", name="pk_stops"),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
            name="fk_stops_version_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "parent_station"],
            ["stops.version_id", "stops.stop_id"],
            name="fk_stops_parent_station",
            ondelete="CASCADE",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index("ix_stops_version_id",      "stops", ["version_id"])
    op.create_index("ix_stops_parent_station",  "stops", ["version_id", "parent_station"])


def downgrade() -> None:
    op.drop_index("ix_stops_parent_station", table_name="stops")
    op.drop_index("ix_stops_version_id",     table_name="stops")
    op.drop_constraint("fk_stops_parent_station", "stops", type_="foreignkey")
    op.drop_table("stops")
