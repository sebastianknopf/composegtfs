"""Drop composite SET NULL foreign keys that reference version_id

Composite FKs with ON DELETE SET NULL on (version_id, ...) tried to null out
version_id (NOT NULL) whenever the referenced row was deleted, causing an
IntegrityError on version deletion.

- fk_routes_agency  : routes(version_id, agency_id) → agencies  SET NULL
- fk_trips_shape    : trips(version_id, shape_id)   → shapes    SET NULL

Both constraints are dropped. Referential integrity at the app level is
preserved: agency_id / shape_id references within the same version are
validated by the application, and both routes and trips are already covered
by their own version-level CASCADE FK.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-14
"""
from __future__ import annotations

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the composite FK that caused SET NULL on version_id in routes
    op.drop_constraint("fk_routes_agency", "routes", type_="foreignkey")

    # Drop the composite FK that caused SET NULL on version_id in trips
    op.drop_constraint("fk_trips_shape", "trips", type_="foreignkey")


def downgrade() -> None:
    op.create_foreign_key(
        "fk_trips_shape",
        "trips",
        "shapes",
        ["version_id", "shape_id"],
        ["version_id", "shape_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_routes_agency",
        "routes",
        "agencies",
        ["version_id", "agency_id"],
        ["version_id", "agency_id"],
        ondelete="SET NULL",
    )
