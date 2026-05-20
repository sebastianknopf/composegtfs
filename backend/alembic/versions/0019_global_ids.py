"""Add global_id column to agencies, routes, stops, and trips

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agencies", sa.Column("global_id", sa.String(255), nullable=True))
    op.add_column("routes",   sa.Column("global_id", sa.String(255), nullable=True))
    op.add_column("stops",    sa.Column("global_id", sa.String(255), nullable=True))
    op.add_column("trips",    sa.Column("global_id", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("trips",    "global_id")
    op.drop_column("stops",    "global_id")
    op.drop_column("routes",   "global_id")
    op.drop_column("agencies", "global_id")
