"""Add routes table (GTFS routes.txt, scoped to version)

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "routes",
        sa.Column("version_id",         UUID(as_uuid=True), nullable=False),
        sa.Column("route_id",           sa.String(255),     nullable=False),
        sa.Column("agency_id",          sa.String(255),     nullable=True),
        sa.Column("route_short_name",   sa.String(255),     nullable=True),
        sa.Column("route_long_name",    sa.String(255),     nullable=True),
        sa.Column("route_desc",         sa.Text(),          nullable=True),
        sa.Column("route_type",         sa.Integer(),       nullable=False),
        sa.Column("route_url",          sa.String(2048),    nullable=True),
        sa.Column("route_color",        sa.String(6),       nullable=True),
        sa.Column("route_text_color",   sa.String(6),       nullable=True),
        sa.Column("route_sort_order",   sa.Integer(),       nullable=True),
        sa.Column("continuous_pickup",  sa.SmallInteger(),  nullable=True),
        sa.Column("continuous_drop_off", sa.SmallInteger(), nullable=True),
        sa.Column("network_id",         sa.String(255),     nullable=True),
        sa.PrimaryKeyConstraint("version_id", "route_id", name="pk_routes"),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
            name="fk_routes_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "agency_id"],
            ["agencies.version_id", "agencies.agency_id"],
            name="fk_routes_agency",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_routes_version_id", "routes", ["version_id"])


def downgrade() -> None:
    op.drop_index("ix_routes_version_id", table_name="routes")
    op.drop_table("routes")
