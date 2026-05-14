"""Add sort_order to versions

Revision ID: 0015
Revises: 0014
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("versions", sa.Column("sort_order", sa.Integer(), nullable=True))
    op.create_index("ix_versions_sort_order", "versions", ["sort_order"])


def downgrade() -> None:
    op.drop_index("ix_versions_sort_order", table_name="versions")
    op.drop_column("versions", "sort_order")
