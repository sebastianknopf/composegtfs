"""GET /api/permissions — returns the full structured permission registry.

This endpoint is authentication-gated but requires no specific permission,
so any logged-in user (or the frontend) can fetch the available permissions
to render assignment UIs (e.g. the GroupEditModal permission checkboxes).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import get_current_user
from app.models import User
from app.permissions import PERMISSION_GROUPS

router = APIRouter(prefix="/api/permissions", tags=["permissions"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class PermissionDefOut(BaseModel):
    codename: str
    lang_key: str


class PermissionGroupOut(BaseModel):
    key: str
    lang_key: str
    permissions: list[PermissionDefOut]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=list[PermissionGroupOut],
    summary="List all available permissions",
)
async def list_permissions(
    _: User = Depends(get_current_user),
) -> list[PermissionGroupOut]:
    """
    Returns the complete permission registry grouped by resource.
    Requires authentication; no specific permission is needed.
    """
    return [
        PermissionGroupOut(
            key=group.key,
            lang_key=group.lang_key,
            permissions=[
                PermissionDefOut(codename=p.codename, lang_key=p.lang_key)
                for p in group.permissions
            ],
        )
        for group in PERMISSION_GROUPS
    ]
