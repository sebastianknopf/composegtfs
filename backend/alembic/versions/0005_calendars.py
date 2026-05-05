"""Add calendars, aux_calendars, aux_calendar_dates, calendar_aux_calendars tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- calendars (GTFS calendar.txt, scoped to version) --------------------
    op.create_table(
        "calendars",
        sa.Column("version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("monday",    sa.SmallInteger(), nullable=False),
        sa.Column("tuesday",   sa.SmallInteger(), nullable=False),
        sa.Column("wednesday", sa.SmallInteger(), nullable=False),
        sa.Column("thursday",  sa.SmallInteger(), nullable=False),
        sa.Column("friday",    sa.SmallInteger(), nullable=False),
        sa.Column("saturday",  sa.SmallInteger(), nullable=False),
        sa.Column("sunday",    sa.SmallInteger(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date",   sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("version_id", "service_id", name="pk_calendars"),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
            name="fk_calendars_version_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_calendars_version_id", "calendars", ["version_id"])

    # -- aux_calendars (Hilfskalender, scoped to version) --------------------
    op.create_table(
        "aux_calendars",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_aux_calendars"),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
            name="fk_aux_calendars_version_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("version_id", "name", name="uq_aux_calendars_version_name"),
    )
    op.create_index("ix_aux_calendars_version_id", "aux_calendars", ["version_id"])

    # -- aux_calendar_dates (individual dates per Hilfskalender) -------------
    op.create_table(
        "aux_calendar_dates",
        sa.Column("aux_calendar_id", UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("aux_calendar_id", "date", name="pk_aux_calendar_dates"),
        sa.ForeignKeyConstraint(
            ["aux_calendar_id"],
            ["aux_calendars.id"],
            name="fk_aux_calendar_dates_aux_calendar_id",
            ondelete="CASCADE",
        ),
    )

    # -- calendar_aux_calendars (junction: Tagesart ↔ Hilfskalender) ---------
    op.create_table(
        "calendar_aux_calendars",
        sa.Column("version_id",      UUID(as_uuid=True), nullable=False),
        sa.Column("service_id",      sa.String(255),     nullable=False),
        sa.Column("aux_calendar_id", UUID(as_uuid=True), nullable=False),
        sa.Column("junction_type",   sa.SmallInteger(),  nullable=False),
        sa.PrimaryKeyConstraint(
            "version_id", "service_id", "aux_calendar_id",
            name="pk_calendar_aux_calendars",
        ),
        sa.ForeignKeyConstraint(
            ["version_id", "service_id"],
            ["calendars.version_id", "calendars.service_id"],
            name="fk_cal_aux_cal_calendar",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["aux_calendar_id"],
            ["aux_calendars.id"],
            name="fk_cal_aux_cal_aux_calendar_id",
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("calendar_aux_calendars")
    op.drop_table("aux_calendar_dates")
    op.drop_index("ix_aux_calendars_version_id", table_name="aux_calendars")
    op.drop_table("aux_calendars")
    op.drop_index("ix_calendars_version_id", table_name="calendars")
    op.drop_table("calendars")
