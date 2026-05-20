from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import Stop, User, Version
from app.permissions import Permission, require
from app.services.reroute_shapes import (
    cleanup_free_coords_around_gaps,
    collect_deletion_context,
    reroute_shapes_by_ids,
    reroute_shapes_for_platform,
)

router = APIRouter(prefix="/api/versions/{version_id}/stops", tags=["stops"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class StopOut(BaseModel):
    version_id:          uuid.UUID
    stop_id:             str
    stop_code:           str | None
    stop_name:           str | None
    tts_stop_name:       str | None
    stop_desc:           str | None
    stop_lat:            float | None
    stop_lon:            float | None
    zone_id:             str | None
    stop_url:            str | None
    location_type:       int | None
    parent_station:      str | None
    stop_timezone:       str | None
    wheelchair_boarding: int | None
    level_id:            str | None
    platform_code:       str | None
    stop_access:         int | None
    global_id:           str | None

    model_config = {"from_attributes": True}


class StopCreate(BaseModel):
    stop_id:             str
    stop_code:           str | None = None
    stop_name:           str | None = None
    tts_stop_name:       str | None = None
    stop_desc:           str | None = None
    stop_lat:            float | None = None
    stop_lon:            float | None = None
    zone_id:             str | None = None
    stop_url:            str | None = None
    location_type:       int | None = None
    stop_timezone:       str | None = None
    wheelchair_boarding: int | None = None
    level_id:            str | None = None
    platform_code:       str | None = None
    stop_access:         int | None = None
    global_id:           str | None = None

    @field_validator("stop_id")
    @classmethod
    def stop_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("stop_id must not be empty")
        if len(v) > 255:
            raise ValueError("stop_id must not exceed 255 characters")
        return v

    @field_validator("stop_lat")
    @classmethod
    def stop_lat_valid(cls, v: float | None) -> float | None:
        if v is not None and not (-90.0 <= v <= 90.0):
            raise ValueError("stop_lat must be between -90.0 and 90.0")
        return v

    @field_validator("stop_lon")
    @classmethod
    def stop_lon_valid(cls, v: float | None) -> float | None:
        if v is not None and not (-180.0 <= v <= 180.0):
            raise ValueError("stop_lon must be between -180.0 and 180.0")
        return v

    @field_validator("location_type")
    @classmethod
    def location_type_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1, 2, 3, 4):
            raise ValueError("location_type must be 0, 1, 2, 3, or 4")
        return v

    @field_validator("wheelchair_boarding")
    @classmethod
    def wheelchair_boarding_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1, 2):
            raise ValueError("wheelchair_boarding must be 0, 1, or 2")
        return v

    @field_validator("stop_access")
    @classmethod
    def stop_access_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1):
            raise ValueError("stop_access must be 0 or 1")
        return v


class StopUpdate(BaseModel):
    stop_code:           str | None = None
    stop_name:           str | None = None
    tts_stop_name:       str | None = None
    stop_desc:           str | None = None
    stop_lat:            float | None = None
    stop_lon:            float | None = None
    zone_id:             str | None = None
    stop_url:            str | None = None
    location_type:       int | None = None
    stop_timezone:       str | None = None
    wheelchair_boarding: int | None = None
    level_id:            str | None = None
    platform_code:       str | None = None
    stop_access:         int | None = None
    global_id:           str | None = None

    @field_validator("stop_lat")
    @classmethod
    def stop_lat_valid(cls, v: float | None) -> float | None:
        if v is not None and not (-90.0 <= v <= 90.0):
            raise ValueError("stop_lat must be between -90.0 and 90.0")
        return v

    @field_validator("stop_lon")
    @classmethod
    def stop_lon_valid(cls, v: float | None) -> float | None:
        if v is not None and not (-180.0 <= v <= 180.0):
            raise ValueError("stop_lon must be between -180.0 and 180.0")
        return v

    @field_validator("location_type")
    @classmethod
    def location_type_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1, 2, 3, 4):
            raise ValueError("location_type must be 0, 1, 2, 3, or 4")
        return v

    @field_validator("wheelchair_boarding")
    @classmethod
    def wheelchair_boarding_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1, 2):
            raise ValueError("wheelchair_boarding must be 0, 1, or 2")
        return v

    @field_validator("stop_access")
    @classmethod
    def stop_access_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1):
            raise ValueError("stop_access must be 0 or 1")
        return v


# Platform (Steig) schemas — subset of Stop, always location_type=0,
# parent_station is set from the URL path parameter.

class PlatformCreate(BaseModel):
    stop_id:             str
    stop_code:           str | None = None
    stop_name:           str | None = None
    tts_stop_name:       str | None = None
    stop_desc:           str | None = None
    stop_lat:            float | None = None
    stop_lon:            float | None = None
    zone_id:             str | None = None
    stop_url:            str | None = None
    stop_timezone:       str | None = None
    wheelchair_boarding: int | None = None
    platform_code:       str | None = None
    stop_access:         int | None = None
    global_id:           str | None = None

    @field_validator("stop_id")
    @classmethod
    def stop_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("stop_id must not be empty")
        if len(v) > 255:
            raise ValueError("stop_id must not exceed 255 characters")
        return v

    @field_validator("stop_lat")
    @classmethod
    def stop_lat_valid(cls, v: float | None) -> float | None:
        if v is not None and not (-90.0 <= v <= 90.0):
            raise ValueError("stop_lat must be between -90.0 and 90.0")
        return v

    @field_validator("stop_lon")
    @classmethod
    def stop_lon_valid(cls, v: float | None) -> float | None:
        if v is not None and not (-180.0 <= v <= 180.0):
            raise ValueError("stop_lon must be between -180.0 and 180.0")
        return v

    @field_validator("wheelchair_boarding")
    @classmethod
    def wheelchair_boarding_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1, 2):
            raise ValueError("wheelchair_boarding must be 0, 1, or 2")
        return v

    @field_validator("stop_access")
    @classmethod
    def stop_access_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1):
            raise ValueError("stop_access must be 0 or 1")
        return v


class PlatformUpdate(BaseModel):
    stop_code:           str | None = None
    stop_name:           str | None = None
    tts_stop_name:       str | None = None
    stop_desc:           str | None = None
    stop_lat:            float | None = None
    stop_lon:            float | None = None
    zone_id:             str | None = None
    stop_url:            str | None = None
    stop_timezone:       str | None = None
    wheelchair_boarding: int | None = None
    platform_code:       str | None = None
    stop_access:         int | None = None
    global_id:           str | None = None

    @field_validator("stop_lat")
    @classmethod
    def stop_lat_valid(cls, v: float | None) -> float | None:
        if v is not None and not (-90.0 <= v <= 90.0):
            raise ValueError("stop_lat must be between -90.0 and 90.0")
        return v

    @field_validator("stop_lon")
    @classmethod
    def stop_lon_valid(cls, v: float | None) -> float | None:
        if v is not None and not (-180.0 <= v <= 180.0):
            raise ValueError("stop_lon must be between -180.0 and 180.0")
        return v

    @field_validator("wheelchair_boarding")
    @classmethod
    def wheelchair_boarding_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1, 2):
            raise ValueError("wheelchair_boarding must be 0, 1, or 2")
        return v

    @field_validator("stop_access")
    @classmethod
    def stop_access_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1):
            raise ValueError("stop_access must be 0 or 1")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_version_or_404(version_id: uuid.UUID, session: AsyncSession) -> Version:
    version = await session.get(Version, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    return version


async def _get_stop_or_404(
    version_id: uuid.UUID,
    stop_id: str,
    session: AsyncSession,
    *,
    require_no_parent: bool = False,
) -> Stop:
    result = await session.execute(
        select(Stop).where(
            Stop.version_id == version_id,
            Stop.stop_id == stop_id,
        )
    )
    stop = result.scalar_one_or_none()
    if stop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stop not found.")
    if require_no_parent and stop.parent_station is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stop not found.")
    return stop


async def _get_platform_or_404(
    version_id: uuid.UUID,
    parent_stop_id: str,
    platform_stop_id: str,
    session: AsyncSession,
) -> Stop:
    result = await session.execute(
        select(Stop).where(
            Stop.version_id == version_id,
            Stop.stop_id == platform_stop_id,
            Stop.parent_station == parent_stop_id,
        )
    )
    platform = result.scalar_one_or_none()
    if platform is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found.")
    return platform


def _apply_nullable_fields(obj: Stop, body: StopUpdate | PlatformUpdate) -> None:
    """Apply all fields from the update body, respecting explicit null assignments."""
    for field in body.model_fields_set:
        setattr(obj, field, getattr(body, field))


# ---------------------------------------------------------------------------
# Stop endpoints (Haltestellen — top-level stops without a parent)
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=list[StopOut],
    summary="List all top-level stops for a version",
    dependencies=[require(Permission.STOPS_READ)],
)
async def list_stops(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Stop]:
    await _get_version_or_404(version_id, session)
    result = await session.execute(
        select(Stop)
        .where(Stop.version_id == version_id, Stop.parent_station.is_(None))
        .order_by(Stop.stop_id)
    )
    return list(result.scalars().all())


@router.get(
    "/all-platforms",
    response_model=list[StopOut],
    summary="List all platforms (Steige) across all stops for a version",
    dependencies=[require(Permission.STOPS_READ)],
)
async def list_all_platforms(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Stop]:
    await _get_version_or_404(version_id, session)
    result = await session.execute(
        select(Stop)
        .where(Stop.version_id == version_id, Stop.parent_station.isnot(None))
        .order_by(Stop.stop_id)
    )
    return list(result.scalars().all())


@router.post(
    "",
    response_model=StopOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new top-level stop within a version",
    dependencies=[require(Permission.STOPS_WRITE)],
)
async def create_stop(
    version_id: uuid.UUID,
    body: StopCreate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Stop:
    await _get_version_or_404(version_id, session)

    existing = await session.execute(
        select(Stop).where(Stop.version_id == version_id, Stop.stop_id == body.stop_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A stop with this ID already exists in the version.",
        )

    stop = Stop(
        version_id=version_id,
        stop_id=body.stop_id,
        stop_code=body.stop_code,
        stop_name=body.stop_name,
        tts_stop_name=body.tts_stop_name,
        stop_desc=body.stop_desc,
        stop_lat=body.stop_lat,
        stop_lon=body.stop_lon,
        zone_id=body.zone_id,
        stop_url=body.stop_url,
        location_type=body.location_type,
        parent_station=None,
        stop_timezone=body.stop_timezone,
        wheelchair_boarding=body.wheelchair_boarding,
        level_id=body.level_id,
        platform_code=body.platform_code,
        stop_access=body.stop_access,
    )
    session.add(stop)
    await session.commit()
    await session.refresh(stop)
    return stop


@router.get(
    "/{stop_id}",
    response_model=StopOut,
    summary="Get a single top-level stop by ID",
    dependencies=[require(Permission.STOPS_READ)],
)
async def get_stop(
    version_id: uuid.UUID,
    stop_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Stop:
    await _get_version_or_404(version_id, session)
    return await _get_stop_or_404(version_id, stop_id, session, require_no_parent=True)


@router.put(
    "/{stop_id}",
    response_model=StopOut,
    summary="Update a top-level stop within a version",
    dependencies=[require(Permission.STOPS_WRITE)],
)
async def update_stop(
    version_id: uuid.UUID,
    stop_id: str,
    body: StopUpdate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Stop:
    await _get_version_or_404(version_id, session)
    stop = await _get_stop_or_404(version_id, stop_id, session, require_no_parent=True)
    _apply_nullable_fields(stop, body)
    await session.commit()
    await session.refresh(stop)
    return stop


@router.delete(
    "/{stop_id}",
    summary="Delete a top-level stop and all its platforms, then re-route affected shapes (SSE)",
    response_class=StreamingResponse,
    dependencies=[require(Permission.STOPS_DELETE)],
)
async def delete_stop(
    version_id: uuid.UUID,
    stop_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    await _get_version_or_404(version_id, session)
    stop = await _get_stop_or_404(version_id, stop_id, session, require_no_parent=True)

    # Collect platform IDs belonging to this stop (must happen before deletion)
    platform_ids_result = await session.execute(
        select(Stop.stop_id).where(Stop.version_id == version_id, Stop.parent_station == stop_id)
    )
    platform_stop_ids = list(platform_ids_result.scalars().all())

    # Collect affected shape IDs and gap info before cascade deletes intermediate points
    shape_ids, gaps = await collect_deletion_context(version_id, platform_stop_ids, session)

    # Delete all child platforms then the parent stop
    await session.execute(
        sa_delete(Stop)
        .where(Stop.version_id == version_id, Stop.parent_station == stop_id)
        .execution_options(synchronize_session=False)
    )
    await session.delete(stop)
    await session.commit()

    # Remove free-coordinate intermediate points orphaned by the deletion
    await cleanup_free_coords_around_gaps(version_id, gaps, session)
    await session.commit()

    async def _generate():
        async for event in reroute_shapes_by_ids(version_id, shape_ids, session):
            yield _sse(event)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Platform endpoints (Steige — location_type=0, nested under a stop)
# ---------------------------------------------------------------------------

@router.get(
    "/{stop_id}/platforms",
    response_model=list[StopOut],
    summary="List all platforms (Steige) of a stop",
    dependencies=[require(Permission.STOPS_READ)],
)
async def list_platforms(
    version_id: uuid.UUID,
    stop_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Stop]:
    await _get_version_or_404(version_id, session)
    await _get_stop_or_404(version_id, stop_id, session, require_no_parent=True)
    result = await session.execute(
        select(Stop)
        .where(Stop.version_id == version_id, Stop.parent_station == stop_id)
        .order_by(Stop.stop_id)
    )
    return list(result.scalars().all())


@router.post(
    "/{stop_id}/platforms",
    response_model=StopOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new platform (Steig) under a stop",
    dependencies=[require(Permission.STOPS_WRITE)],
)
async def create_platform(
    version_id: uuid.UUID,
    stop_id: str,
    body: PlatformCreate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Stop:
    await _get_version_or_404(version_id, session)
    await _get_stop_or_404(version_id, stop_id, session, require_no_parent=True)

    existing = await session.execute(
        select(Stop).where(Stop.version_id == version_id, Stop.stop_id == body.stop_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A stop with this ID already exists in the version.",
        )

    platform = Stop(
        version_id=version_id,
        stop_id=body.stop_id,
        stop_code=body.stop_code,
        stop_name=body.stop_name,
        tts_stop_name=body.tts_stop_name,
        stop_desc=body.stop_desc,
        stop_lat=body.stop_lat,
        stop_lon=body.stop_lon,
        zone_id=body.zone_id,
        stop_url=body.stop_url,
        location_type=0,
        parent_station=stop_id,
        stop_timezone=body.stop_timezone,
        wheelchair_boarding=body.wheelchair_boarding,
        level_id=None,
        platform_code=body.platform_code,
        stop_access=body.stop_access,
    )
    session.add(platform)
    await session.commit()
    await session.refresh(platform)
    return platform


@router.get(
    "/{stop_id}/platforms/{platform_stop_id}",
    response_model=StopOut,
    summary="Get a single platform (Steig) of a stop",
    dependencies=[require(Permission.STOPS_READ)],
)
async def get_platform(
    version_id: uuid.UUID,
    stop_id: str,
    platform_stop_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Stop:
    await _get_version_or_404(version_id, session)
    await _get_stop_or_404(version_id, stop_id, session, require_no_parent=True)
    return await _get_platform_or_404(version_id, stop_id, platform_stop_id, session)


def _sse(event_dict: dict) -> str:
    """Encode a dict as a single SSE data line."""
    return f"data: {json.dumps(event_dict, ensure_ascii=False)}\n\n"


@router.put(
    "/{stop_id}/platforms/{platform_stop_id}",
    summary="Update a platform (Steig) of a stop and re-route affected shapes (SSE)",
    response_class=StreamingResponse,
    dependencies=[require(Permission.STOPS_WRITE)],
)
async def update_platform(
    version_id: uuid.UUID,
    stop_id: str,
    platform_stop_id: str,
    body: PlatformUpdate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    await _get_version_or_404(version_id, session)
    await _get_stop_or_404(version_id, stop_id, session, require_no_parent=True)
    platform = await _get_platform_or_404(version_id, stop_id, platform_stop_id, session)

    # Capture old position before applying changes
    old_lat = platform.stop_lat
    old_lon = platform.stop_lon

    _apply_nullable_fields(platform, body)
    await session.commit()
    await session.refresh(platform)

    position_changed = (old_lat != platform.stop_lat or old_lon != platform.stop_lon)

    platform_dict = StopOut.model_validate(platform).model_dump(mode="json")

    async def _generate():
        if position_changed:
            async for event in reroute_shapes_for_platform(version_id, platform_stop_id, session):
                yield _sse(event)
        else:
            yield _sse({"type": "done", "total": 0, "platform": platform_dict})
            return
        # After rerouting stream finishes, emit final done with platform data
        yield _sse({"type": "done", "platform": platform_dict})

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete(
    "/{stop_id}/platforms/{platform_stop_id}",
    summary="Delete a platform (Steig) of a stop and re-route affected shapes (SSE)",
    response_class=StreamingResponse,
    dependencies=[require(Permission.STOPS_DELETE)],
)
async def delete_platform(
    version_id: uuid.UUID,
    stop_id: str,
    platform_stop_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    await _get_version_or_404(version_id, session)
    await _get_stop_or_404(version_id, stop_id, session, require_no_parent=True)
    platform = await _get_platform_or_404(version_id, stop_id, platform_stop_id, session)

    # Collect affected shape IDs and gap info before the cascade deletes intermediate points
    shape_ids, gaps = await collect_deletion_context(version_id, [platform_stop_id], session)

    await session.delete(platform)
    await session.commit()

    # Remove free-coordinate intermediate points orphaned by the deletion
    await cleanup_free_coords_around_gaps(version_id, gaps, session)
    await session.commit()

    async def _generate():
        async for event in reroute_shapes_by_ids(version_id, shape_ids, session):
            yield _sse(event)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

