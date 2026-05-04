from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import User, Version
from app.permissions import Permission, require

router = APIRouter(prefix="/api/versions", tags=["versions"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VersionOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class VersionCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        if len(v) > 128:
            raise ValueError("name must not exceed 128 characters")
        return v


class VersionRename(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        if len(v) > 128:
            raise ValueError("name must not exceed 128 characters")
        return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=list[VersionOut],
    summary="List all versions",
)
async def list_versions(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Version]:
    result = await session.execute(select(Version).order_by(Version.created_at))
    return list(result.scalars().all())


@router.post(
    "",
    response_model=VersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new version",
    dependencies=[require(Permission.VERSIONS_WRITE)],
)
async def create_version(
    body: VersionCreate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Version:
    # Check for duplicate name
    existing = await session.execute(select(Version).where(Version.name == body.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A version with this name already exists.",
        )

    version = Version(name=body.name)
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return version


@router.get(
    "/{version_id}",
    response_model=VersionOut,
    summary="Get a single version by ID",
    dependencies=[require(Permission.VERSIONS_READ)],
)
async def get_version(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Version:
    version = await session.get(Version, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    return version


@router.delete(
    "/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a version",
    dependencies=[require(Permission.VERSIONS_DELETE)],
)
async def delete_version(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    version = await session.get(Version, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")

    # Prevent deleting the last remaining version
    count_result = await session.execute(select(func.count()).select_from(Version))
    if count_result.scalar_one() <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete the last remaining version.",
        )

    await session.delete(version)
    await session.commit()


@router.patch(
    "/{version_id}",
    response_model=VersionOut,
    summary="Rename a version",
    dependencies=[require(Permission.VERSIONS_WRITE)],
)
async def rename_version(
    version_id: uuid.UUID,
    body: VersionRename,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Version:
    version = await session.get(Version, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")

    if body.name != version.name:
        existing = await session.execute(select(Version).where(Version.name == body.name))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A version with this name already exists.",
            )

    version.name = body.name
    await session.commit()
    await session.refresh(version)
    return version
