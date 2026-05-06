"""Add cemv_support column to routes table

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("routes", sa.Column("cemv_support", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("routes", "cemv_support")
