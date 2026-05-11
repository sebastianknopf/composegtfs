"""Add composite foreign key from trips to shapes with SET NULL

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add composite foreign key from trips to shapes with ON DELETE SET NULL
    op.create_foreign_key(
        "fk_trips_shape",
        "trips",
        "shapes",
        ["version_id", "shape_id"],
        ["version_id", "shape_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Remove the foreign key
    op.drop_constraint("fk_trips_shape", "trips", type_="foreignkey")
