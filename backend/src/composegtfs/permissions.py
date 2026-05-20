"""
Permission system.

Permissions are defined purely in code as a two-level hierarchy:
  resource group  (e.g. "accounts")
    └─ permission (e.g. "accounts:read")

Each PermissionDef carries the technical codename (stored in the DB) and the
i18n lang_key used by the frontend to resolve the human-readable label.

The require() factory returns a FastAPI Depends that:
  - passes immediately for superusers
  - checks the union of all granted permissions across the user's groups
  - raises HTTP 403 if the required permission is not present
  - HTTP 401 / user-inactive is handled upstream by get_current_user
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from composegtfs.auth import get_current_user
from composegtfs.database import get_session
from composegtfs.models import GroupPermission, User


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PermissionDef:
    """A single permission with its codename and frontend i18n key."""
    codename: str   # e.g. "accounts:read"
    lang_key: str   # e.g. "permissions.accounts.read"


@dataclass(frozen=True)
class PermissionGroup:
    """A logical grouping of related permissions (maps to one resource)."""
    key: str                             # e.g. "accounts"
    lang_key: str                        # e.g. "permissions._groups.accounts"
    permissions: Sequence[PermissionDef]


# ---------------------------------------------------------------------------
# Permission registry
# ---------------------------------------------------------------------------

PERMISSION_GROUPS: list[PermissionGroup] = [
    PermissionGroup(
        key="accounts",
        lang_key="permissions._groups.accounts",
        permissions=[
            PermissionDef("accounts:read",          "permissions.accounts.read"),
            PermissionDef("accounts:write",         "permissions.accounts.write"),
            PermissionDef("accounts:delete",        "permissions.accounts.delete"),
            PermissionDef("accounts:assign_groups", "permissions.accounts.assign_groups"),
        ],
    ),
    PermissionGroup(
        key="groups",
        lang_key="permissions._groups.groups",
        permissions=[
            PermissionDef("groups:read",               "permissions.groups.read"),
            PermissionDef("groups:write",              "permissions.groups.write"),
            PermissionDef("groups:delete",             "permissions.groups.delete"),
            PermissionDef("groups:assign_permissions", "permissions.groups.assign_permissions"),
        ],
    ),
    PermissionGroup(
        key="settings",
        lang_key="permissions._groups.settings",
        permissions=[
            PermissionDef("settings:read",  "permissions.settings.read"),
            PermissionDef("settings:write", "permissions.settings.write"),
        ],
    ),
    PermissionGroup(
        key="versions",
        lang_key="permissions._groups.versions",
        permissions=[
            PermissionDef("versions:read",   "permissions.versions.read"),
            PermissionDef("versions:write",  "permissions.versions.write"),
            PermissionDef("versions:delete", "permissions.versions.delete"),
        ],
    ),
    PermissionGroup(
        key="network",
        lang_key="permissions._groups.network",
        permissions=[
            PermissionDef("network:read",  "permissions.network.read"),
            PermissionDef("network:write", "permissions.network.write"),
        ],
    ),
    PermissionGroup(
        key="schedule",
        lang_key="permissions._groups.schedule",
        permissions=[
            PermissionDef("schedule:read",   "permissions.schedule.read"),
            PermissionDef("schedule:write",  "permissions.schedule.write"),
            PermissionDef("schedule:delete", "permissions.schedule.delete"),
        ],
    ),
    PermissionGroup(
        key="agency",
        lang_key="permissions._groups.agency",
        permissions=[
            PermissionDef("agency:read",   "permissions.agency.read"),
            PermissionDef("agency:write",  "permissions.agency.write"),
            PermissionDef("agency:delete", "permissions.agency.delete"),
        ],
    ),
    PermissionGroup(
        key="calendar",
        lang_key="permissions._groups.calendar",
        permissions=[
            PermissionDef("calendar:read",   "permissions.calendar.read"),
            PermissionDef("calendar:write",  "permissions.calendar.write"),
            PermissionDef("calendar:delete", "permissions.calendar.delete"),
        ],
    ),
    PermissionGroup(
        key="stops",
        lang_key="permissions._groups.stops",
        permissions=[
            PermissionDef("stops:read",   "permissions.stops.read"),
            PermissionDef("stops:write",  "permissions.stops.write"),
            PermissionDef("stops:delete", "permissions.stops.delete"),
        ],
    ),
    PermissionGroup(
        key="routes",
        lang_key="permissions._groups.routes",
        permissions=[
            PermissionDef("routes:read",   "permissions.routes.read"),
            PermissionDef("routes:write",  "permissions.routes.write"),
            PermissionDef("routes:delete", "permissions.routes.delete"),
        ],
    ),
    PermissionGroup(
        key="shapes",
        lang_key="permissions._groups.shapes",
        permissions=[
            PermissionDef("shapes:read",   "permissions.shapes.read"),
            PermissionDef("shapes:write",  "permissions.shapes.write"),
            PermissionDef("shapes:delete", "permissions.shapes.delete"),
        ],
    ),
    PermissionGroup(
        key="gtfs",
        lang_key="permissions._groups.gtfs",
        permissions=[
            PermissionDef("gtfs:export", "permissions.gtfs.export"),
        ],
    ),
    PermissionGroup(
        key="headsigns",
        lang_key="permissions._groups.headsigns",
        permissions=[
            PermissionDef("headsigns:read",   "permissions.headsigns.read"),
            PermissionDef("headsigns:write",  "permissions.headsigns.write"),
            PermissionDef("headsigns:delete", "permissions.headsigns.delete"),
        ],
    ),
]

# Flat set of all valid codenames — used for validation on write
ALL_CODENAMES: frozenset[str] = frozenset(
    p.codename
    for g in PERMISSION_GROUPS
    for p in g.permissions
)


# ---------------------------------------------------------------------------
# Enum for type-safe use in require()
# ---------------------------------------------------------------------------

class Permission(str, Enum):
    # Accounts
    ACCOUNTS_READ          = "accounts:read"
    ACCOUNTS_WRITE         = "accounts:write"
    ACCOUNTS_DELETE        = "accounts:delete"
    ACCOUNTS_ASSIGN_GROUPS = "accounts:assign_groups"

    # Groups
    GROUPS_READ               = "groups:read"
    GROUPS_WRITE              = "groups:write"
    GROUPS_DELETE             = "groups:delete"
    GROUPS_ASSIGN_PERMISSIONS = "groups:assign_permissions"

    # Settings
    SETTINGS_READ  = "settings:read"
    SETTINGS_WRITE = "settings:write"

    # Versions
    VERSIONS_READ   = "versions:read"
    VERSIONS_WRITE  = "versions:write"
    VERSIONS_DELETE = "versions:delete"

    # Network (GTFS)
    NETWORK_READ  = "network:read"
    NETWORK_WRITE = "network:write"

    # Schedule (GTFS)
    SCHEDULE_READ   = "schedule:read"
    SCHEDULE_WRITE  = "schedule:write"
    SCHEDULE_DELETE = "schedule:delete"

    # Agency (GTFS)
    AGENCY_READ   = "agency:read"
    AGENCY_WRITE  = "agency:write"
    AGENCY_DELETE = "agency:delete"

    # Calendar (GTFS)
    CALENDAR_READ   = "calendar:read"
    CALENDAR_WRITE  = "calendar:write"
    CALENDAR_DELETE = "calendar:delete"

    # Stops (GTFS)
    STOPS_READ   = "stops:read"
    STOPS_WRITE  = "stops:write"
    STOPS_DELETE = "stops:delete"

    # Routes (GTFS)
    ROUTES_READ   = "routes:read"
    ROUTES_WRITE  = "routes:write"
    ROUTES_DELETE = "routes:delete"

    # Shapes / Fahrwege (network area)
    SHAPES_READ   = "shapes:read"
    SHAPES_WRITE  = "shapes:write"
    SHAPES_DELETE = "shapes:delete"

    # GTFS Export
    GTFS_EXPORT = "gtfs:export"

    # Headsigns
    HEADSIGNS_READ   = "headsigns:read"
    HEADSIGNS_WRITE  = "headsigns:write"
    HEADSIGNS_DELETE = "headsigns:delete"


# ---------------------------------------------------------------------------
# require() — FastAPI dependency factory
# ---------------------------------------------------------------------------

def require(permission: Permission) -> Depends:
    """
    Return a FastAPI Depends that enforces a single permission.

    Usage:
        @router.get("", dependencies=[require(Permission.ACCOUNTS_READ)])
        async def list_users(...):
            ...
    """
    async def _dependency(
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        # Superusers bypass all permission checks
        if current_user.is_superuser:
            return

        group_ids = [g.id for g in current_user.groups]
        if not group_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        result = await session.execute(
            select(GroupPermission.permission).where(
                GroupPermission.group_id.in_(group_ids)
            )
        )
        granted: set[str] = {row[0] for row in result.all()}

        # Permission is a str subclass, so direct string comparison works
        if permission not in granted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

    return Depends(_dependency)
