from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import func, nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from composegtfs.auth import get_current_user
from composegtfs.database import get_session
from composegtfs.models import User, Version
from composegtfs.permissions import Permission, require
from composegtfs.services.version_copy import run_copy

router = APIRouter(prefix="/api/versions", tags=["versions"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VersionOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    sort_order: int | None = None

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


class VersionsReorderRequest(BaseModel):
    ordered_ids: list[uuid.UUID]


class CopyIncludes(BaseModel):
    agencies:     bool = False
    day_types:    bool = False
    headsigns:    bool = False
    stops:        bool = False
    shapes:       bool = False
    routes:       bool = False
    route_bands:  bool = False
    schedule:     bool = False


class VersionCopyRequest(BaseModel):
    """Either *name* (create new version) or *target_version_id* (merge into
    existing) must be supplied — but not both."""
    name: str | None = None
    target_version_id: uuid.UUID | None = None
    include: CopyIncludes

    @model_validator(mode="after")
    def validate_target(self) -> "VersionCopyRequest":
        has_name   = self.name is not None
        has_target = self.target_version_id is not None
        if not has_name and not has_target:
            raise ValueError("Either 'name' or 'target_version_id' must be provided")
        if has_name and has_target:
            raise ValueError("Provide only one of 'name' or 'target_version_id'")
        if has_name:
            name = self.name.strip()  # type: ignore[union-attr]
            if not name:
                raise ValueError("name must not be empty")
            if len(name) > 128:
                raise ValueError("name must not exceed 128 characters")
            self.name = name
        return self


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
    result = await session.execute(
        select(Version).order_by(nullslast(Version.sort_order), Version.name)
    )
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


@router.put(
    "/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reorder versions by assigning sort_order",
    dependencies=[require(Permission.VERSIONS_WRITE)],
)
async def reorder_versions(
    body: VersionsReorderRequest,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    for i, version_id in enumerate(body.ordered_ids):
        version = await session.get(Version, version_id)
        if version is not None:
            version.sort_order = i
    await session.commit()


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


def _sse(event_dict: dict) -> str:
    return f"data: {json.dumps(event_dict, ensure_ascii=False)}\n\n"


@router.post(
    "/{version_id}/copy",
    summary="Copy a version (SSE stream)",
    dependencies=[require(Permission.VERSIONS_WRITE)],
    response_class=StreamingResponse,
)
async def copy_version(
    version_id: uuid.UUID,
    body: VersionCopyRequest,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    source = await session.get(Version, version_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")

    if body.target_version_id is not None:
        if body.target_version_id == version_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot copy a version into itself.",
            )
        target = await session.get(Version, body.target_version_id)
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target version not found.",
            )

    async def _generate():
        async for event in run_copy(
            source_version_id=version_id,
            new_name=body.name,
            target_version_id=body.target_version_id,
            include_agencies=body.include.agencies,
            include_day_types=body.include.day_types,
            include_headsigns=body.include.headsigns,
            include_stops=body.include.stops,
            include_shapes=body.include.shapes,
            include_routes=body.include.routes,
            include_route_bands=body.include.route_bands,
            include_schedule=body.include.schedule,
            session=session,
        ):
            yield _sse(event)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
