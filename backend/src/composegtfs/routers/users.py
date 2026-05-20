from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from composegtfs.auth import get_current_user, hash_password
from composegtfs.database import get_session
from composegtfs.models import Group, User
from composegtfs.permissions import Permission, require

router = APIRouter(prefix="/api/users", tags=["users"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    is_active: bool
    is_superuser: bool
    group_ids: list[uuid.UUID]
    created_at: str

    @classmethod
    def from_orm(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            username=user.username,
            email=user.email,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            group_ids=[g.id for g in user.groups],
            created_at=user.created_at.date().isoformat(),
        )

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    is_active: bool = True
    is_superuser: bool = False
    group_ids: list[uuid.UUID] = []


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    group_ids: Optional[list[uuid.UUID]] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[UserOut], summary="List all users")
async def list_users(
    _: User = Depends(get_current_user),
    __: None = require(Permission.ACCOUNTS_READ),
    session: AsyncSession = Depends(get_session),
) -> list[UserOut]:
    result = await session.execute(
        select(User).order_by(User.username).options(selectinload(User.groups))
    )
    return [UserOut.from_orm(u) for u in result.scalars().all()]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Create user")
async def create_user(
    body: UserCreate,
    current_user: User = Depends(get_current_user),
    _: None = require(Permission.ACCOUNTS_WRITE),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    # Only superusers may create another superuser
    if body.is_superuser and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can grant superuser privileges",
        )
    # Check uniqueness
    dup = await session.execute(
        select(User).where((User.username == body.username) | (User.email == body.email))
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username or e-mail already taken")

    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
        is_active=body.is_active,
        is_superuser=body.is_superuser,
    )
    session.add(user)

    if body.group_ids:
        group_result = await session.execute(
            select(Group).where(Group.id.in_(body.group_ids))
        )
        user.groups = list(group_result.scalars().all())

    await session.commit()
    fresh = await session.execute(
        select(User).where(User.username == body.username).options(selectinload(User.groups))
    )
    return UserOut.from_orm(fresh.scalar_one())


@router.put("/{user_id}", response_model=UserOut, summary="Update user")
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    _: None = require(Permission.ACCOUNTS_WRITE),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    result = await session.execute(
        select(User).where(User.id == user_id).options(selectinload(User.groups))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.username is not None:
        # Check for conflict with another user
        dup = await session.execute(
            select(User).where(User.username == body.username, User.id != user_id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
        user.username = body.username

    if body.email is not None:
        dup = await session.execute(
            select(User).where(User.email == body.email, User.id != user_id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail already taken")
        user.email = body.email

    if body.password:
        user.hashed_password = hash_password(body.password)

    if body.is_active is not None:
        user.is_active = body.is_active

    if body.is_superuser is not None:
        # Only superusers may grant or revoke superuser privileges
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only superusers can change superuser privileges",
            )
        # A superuser may not remove their own superuser flag
        if current_user.id == user_id and not body.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot remove superuser privileges from your own account",
            )
        user.is_superuser = body.is_superuser

    if body.group_ids is not None:
        group_result = await session.execute(
            select(Group).where(Group.id.in_(body.group_ids))
        )
        user.groups = list(group_result.scalars().all())

    await session.commit()
    fresh = await session.execute(
        select(User).where(User.id == user_id).options(selectinload(User.groups))
    )
    return UserOut.from_orm(fresh.scalar_one())


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete user")
async def delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    _: None = require(Permission.ACCOUNTS_DELETE),
    session: AsyncSession = Depends(get_session),
) -> None:
    if current_user.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete a superuser account")

    await session.delete(user)
    await session.commit()
