"""Add routed_polyline column to shapes table

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shapes",
        sa.Column("routed_polyline", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shapes", "routed_polyline")
