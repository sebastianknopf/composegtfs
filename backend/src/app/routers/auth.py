from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import authenticate_user, create_access_token, get_current_user
from app.database import get_session
from app.models import GroupPermission, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    username: str
    is_superuser: bool
    permission_codenames: list[str]


@router.post("/token", response_model=TokenResponse, summary="Obtain access token")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user = await authenticate_user(form_data.username, form_data.password, session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=user.username)
    return TokenResponse(access_token=token)


@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
async def refresh(
    current_user: User = Depends(get_current_user),
) -> TokenResponse:
    """Issue a fresh token for the currently authenticated user."""
    token = create_access_token(subject=current_user.username)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse, summary="Current user info + effective permissions")
async def me(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    """Return the authenticated user's effective permissions (union across all groups)."""
    if current_user.is_superuser:
        # Superusers implicitly have every permission — return all codenames
        from app.permissions import ALL_CODENAMES
        codenames = sorted(ALL_CODENAMES)
    else:
        # Load groups lazily if needed
        from app.models import UserGroup
        group_id_result = await session.execute(
            select(UserGroup.group_id).where(UserGroup.user_id == current_user.id)
        )
        group_ids = [row[0] for row in group_id_result.all()]
        if group_ids:
            perm_result = await session.execute(
                select(GroupPermission.permission).where(
                    GroupPermission.group_id.in_(group_ids)
                ).distinct()
            )
            codenames = sorted({row[0] for row in perm_result.all()})
        else:
            codenames = []

    return MeResponse(
        username=current_user.username,
        is_superuser=current_user.is_superuser,
        permission_codenames=codenames,
    )
