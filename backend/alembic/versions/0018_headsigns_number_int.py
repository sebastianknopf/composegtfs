"""Change headsigns.number from VARCHAR(64) to INTEGER

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE headsigns
        ALTER COLUMN number TYPE INTEGER
        USING CASE WHEN number ~ '^\\d+$' THEN number::INTEGER ELSE NULL END
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE headsigns
        ALTER COLUMN number TYPE VARCHAR(64)
        USING number::VARCHAR
        """
    )
