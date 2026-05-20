from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from composegtfs.auth import get_current_user
from composegtfs.database import get_session
from composegtfs.models import Group, GroupPermission, User, UserGroup
from composegtfs.permissions import ALL_CODENAMES, Permission, require

router = APIRouter(prefix="/api/groups", tags=["groups"])


class GroupOut(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    members: int
    permission_codenames: list[str]
    created_at: str


class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permission_codenames: list[str] = []

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Group name is required")
        return cleaned

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permission_codenames: Optional[list[str]] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Group name cannot be empty")
        return cleaned

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None


async def _group_to_out(session: AsyncSession, group: Group) -> GroupOut:
    member_count_result = await session.execute(
        select(func.count(UserGroup.user_id)).where(UserGroup.group_id == group.id)
    )
    member_count = int(member_count_result.scalar_one() or 0)

    perm_result = await session.execute(
        select(GroupPermission.permission).where(GroupPermission.group_id == group.id)
    )
    permission_codenames = [row[0] for row in perm_result.all()]

    return GroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        members=member_count,
        permission_codenames=permission_codenames,
        created_at=group.created_at.date().isoformat(),
    )


@router.get("", response_model=list[GroupOut], summary="List all groups")
async def list_groups(
    _: User = Depends(get_current_user),
    __: None = require(Permission.GROUPS_READ),
    session: AsyncSession = Depends(get_session),
) -> list[GroupOut]:
    result = await session.execute(select(Group).order_by(Group.name))
    groups = result.scalars().all()
    return [await _group_to_out(session, group) for group in groups]


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED, summary="Create group")
async def create_group(
    body: GroupCreate,
    _: User = Depends(get_current_user),
    __: None = require(Permission.GROUPS_WRITE),
    session: AsyncSession = Depends(get_session),
) -> GroupOut:
    dup = await session.execute(select(Group).where(Group.name == body.name))
    if dup.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group name already taken")

    invalid = [c for c in body.permission_codenames if c not in ALL_CODENAMES]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown permission codename(s): {', '.join(invalid)}",
        )

    group = Group(name=body.name, description=body.description)
    session.add(group)
    await session.flush()  # get group.id before inserting permissions

    for codename in body.permission_codenames:
        session.add(GroupPermission(group_id=group.id, permission=codename))

    await session.commit()
    await session.refresh(group)
    return await _group_to_out(session, group)


@router.put("/{group_id}", response_model=GroupOut, summary="Update group")
async def update_group(
    group_id: uuid.UUID,
    body: GroupUpdate,
    _: User = Depends(get_current_user),
    __: None = require(Permission.GROUPS_WRITE),
    session: AsyncSession = Depends(get_session),
) -> GroupOut:
    result = await session.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    if body.name is not None:
        dup = await session.execute(select(Group).where(Group.name == body.name, Group.id != group_id))
        if dup.scalar_one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group name already taken")
        group.name = body.name

    if body.description is not None:
        group.description = body.description

    if body.permission_codenames is not None:
        invalid = [c for c in body.permission_codenames if c not in ALL_CODENAMES]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown permission codename(s): {', '.join(invalid)}",
            )
        await session.execute(
            delete(GroupPermission).where(GroupPermission.group_id == group_id)
        )
        for codename in body.permission_codenames:
            session.add(GroupPermission(group_id=group_id, permission=codename))

    await session.commit()
    await session.refresh(group)
    return await _group_to_out(session, group)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete group")
async def delete_group(
    group_id: uuid.UUID,
    _: User = Depends(get_current_user),
    __: None = require(Permission.GROUPS_DELETE),
    session: AsyncSession = Depends(get_session),
) -> None:
    result = await session.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    await session.delete(group)
    await session.commit()
