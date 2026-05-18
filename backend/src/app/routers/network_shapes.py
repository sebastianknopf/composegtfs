"""
Network-area endpoints for Fahrwege (Shapes).

These endpoints are separate from the schedule-area shape endpoints and
use their own shapes:read / shapes:write / shapes:delete permissions.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import Shape, ShapeIntermediatePoint, Trip, User, Version
from app.permissions import Permission, require

router = APIRouter(
    prefix="/api/versions/{version_id}/network/shapes",
    tags=["network-shapes"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class IntermediatePointOut(BaseModel):
    id: uuid.UUID
    sort_order: int
    lat: float | None
    lon: float | None
    stop_id: str | None

    model_config = {"from_attributes": True}


class IntermediatePointIn(BaseModel):
    sort_order: int
    lat: float | None = None
    lon: float | None = None
    stop_id: str | None = None


class ShapeListOut(BaseModel):
    """Lightweight shape representation used by the list endpoint (no intermediate points)."""
    version_id:          uuid.UUID
    shape_id:            str
    shape_name:          str | None
    shape_polyline:      str
    routed_polyline:     str | None
    description:         str | None
    route_type:          int | None
    is_autoroute_active: bool

    model_config = {"from_attributes": True}


class ShapeOut(ShapeListOut):
    """Full shape representation including intermediate points."""
    intermediate_points: list[IntermediatePointOut] = []


class ShapeUpdate(BaseModel):
    shape_name:           str | None = None
    description:          str | None = None
    route_type:           int | None = None
    is_autoroute_active:  bool | None = None
    # When provided (even as an empty list), replaces all intermediate points.
    # When absent (None), intermediate points are left unchanged.
    intermediate_points:  list[IntermediatePointIn] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_version_or_404(version_id: uuid.UUID, session: AsyncSession) -> Version:
    result = await session.execute(
        select(Version).where(Version.id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )
    return version


async def _get_shape_or_404(
    version_id: uuid.UUID,
    shape_id: str,
    session: AsyncSession,
    *,
    with_points: bool = False,
) -> Shape:
    q = select(Shape).where(
        Shape.version_id == version_id,
        Shape.shape_id == shape_id,
    )
    if with_points:
        q = q.options(selectinload(Shape.intermediate_points))
    result = await session.execute(q)
    shape = result.scalar_one_or_none()
    if shape is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shape not found",
        )
    return shape


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=list[ShapeListOut],
    summary="List all shapes in a version (network area)",
    dependencies=[require(Permission.SHAPES_READ)],
)
async def list_shapes(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Shape]:
    await _get_version_or_404(version_id, session)
    result = await session.execute(
        select(Shape)
        .where(Shape.version_id == version_id)
        .order_by(Shape.shape_name.nulls_last(), Shape.shape_id)
    )
    return list(result.scalars().all())


@router.get(
    "/{shape_id}",
    response_model=ShapeOut,
    summary="Get a single shape including its intermediate points (network area)",
    dependencies=[require(Permission.SHAPES_READ)],
)
async def get_shape(
    version_id: uuid.UUID,
    shape_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Shape:
    await _get_version_or_404(version_id, session)
    return await _get_shape_or_404(version_id, shape_id, session, with_points=True)


@router.patch(
    "/{shape_id}",
    response_model=ShapeOut,
    summary="Update metadata and/or intermediate points of a shape (network area)",
    dependencies=[require(Permission.SHAPES_WRITE)],
)
async def update_shape(
    version_id: uuid.UUID,
    shape_id: str,
    body: ShapeUpdate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Shape:
    await _get_version_or_404(version_id, session)
    shape = await _get_shape_or_404(version_id, shape_id, session)

    if body.shape_name is not None:
        shape.shape_name = body.shape_name.strip() or None
    if body.description is not None:
        shape.description = body.description.strip() or None
    if body.route_type is not None:
        shape.route_type = body.route_type
    if body.is_autoroute_active is not None:
        shape.is_autoroute_active = body.is_autoroute_active

    if body.intermediate_points is not None:
        # Atomically replace all intermediate points for this shape.
        await session.execute(
            delete(ShapeIntermediatePoint)
            .where(
                ShapeIntermediatePoint.version_id == version_id,
                ShapeIntermediatePoint.shape_id == shape_id,
            )
            .execution_options(synchronize_session=False)
        )
        for pt in body.intermediate_points:
            session.add(ShapeIntermediatePoint(
                version_id=version_id,
                shape_id=shape_id,
                sort_order=pt.sort_order,
                lat=pt.lat,
                lon=pt.lon,
                stop_id=pt.stop_id or None,
            ))

    await session.commit()

    # Re-fetch with eager-loaded intermediate_points so the response is complete.
    return await _get_shape_or_404(version_id, shape_id, session, with_points=True)


@router.delete(
    "/{shape_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a shape and detach it from trips (network area)",
    dependencies=[require(Permission.SHAPES_DELETE)],
)
async def delete_shape(
    version_id: uuid.UUID,
    shape_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await _get_version_or_404(version_id, session)
    shape = await _get_shape_or_404(version_id, shape_id, session)
    # Detach shape from all trips before deleting
    await session.execute(
        update(Trip)
        .where(Trip.version_id == version_id, Trip.shape_id == shape_id)
        .values(shape_id=None)
        .execution_options(synchronize_session="fetch")
    )
    await session.delete(shape)
    await session.commit()

router = APIRouter(
    prefix="/api/versions/{version_id}/network/shapes",
    tags=["network-shapes"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ShapeOut(BaseModel):
    version_id:          uuid.UUID
    shape_id:            str
    shape_name:          str | None
    shape_polyline:      str
    routed_polyline:     str | None
    description:         str | None
    route_type:          int | None
    is_autoroute_active: bool

    model_config = {"from_attributes": True}


class ShapeUpdate(BaseModel):
    shape_name:          str | None = None
    description:         str | None = None
    route_type:          int | None = None
    is_autoroute_active: bool | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_version_or_404(version_id: uuid.UUID, session: AsyncSession) -> Version:
    result = await session.execute(
        select(Version).where(Version.id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found",
        )
    return version


async def _get_shape_or_404(
    version_id: uuid.UUID,
    shape_id: str,
    session: AsyncSession,
) -> Shape:
    result = await session.execute(
        select(Shape).where(
            Shape.version_id == version_id,
            Shape.shape_id == shape_id,
        )
    )
    shape = result.scalar_one_or_none()
    if shape is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shape not found",
        )
    return shape


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=list[ShapeOut],
    summary="List all shapes in a version (network area)",
    dependencies=[require(Permission.SHAPES_READ)],
)
async def list_shapes(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Shape]:
    await _get_version_or_404(version_id, session)
    result = await session.execute(
        select(Shape)
        .where(Shape.version_id == version_id)
        .order_by(Shape.shape_name.nulls_last(), Shape.shape_id)
    )
    return list(result.scalars().all())


@router.get(
    "/{shape_id}",
    response_model=ShapeOut,
    summary="Get a single shape (network area)",
    dependencies=[require(Permission.SHAPES_READ)],
)
async def get_shape(
    version_id: uuid.UUID,
    shape_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Shape:
    await _get_version_or_404(version_id, session)
    return await _get_shape_or_404(version_id, shape_id, session)


@router.patch(
    "/{shape_id}",
    response_model=ShapeOut,
    summary="Update metadata of a shape (network area)",
    dependencies=[require(Permission.SHAPES_WRITE)],
)
async def update_shape(
    version_id: uuid.UUID,
    shape_id: str,
    body: ShapeUpdate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Shape:
    await _get_version_or_404(version_id, session)
    shape = await _get_shape_or_404(version_id, shape_id, session)
    if body.shape_name is not None:
        shape.shape_name = body.shape_name.strip() or None
    if body.description is not None:
        shape.description = body.description.strip() or None
    if body.route_type is not None:
        shape.route_type = body.route_type
    if body.is_autoroute_active is not None:
        shape.is_autoroute_active = body.is_autoroute_active
    await session.commit()
    await session.refresh(shape)
    return shape


@router.delete(
    "/{shape_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a shape and detach it from trips (network area)",
    dependencies=[require(Permission.SHAPES_DELETE)],
)
async def delete_shape(
    version_id: uuid.UUID,
    shape_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await _get_version_or_404(version_id, session)
    shape = await _get_shape_or_404(version_id, shape_id, session)
    # Detach shape from all trips before deleting
    await session.execute(
        update(Trip)
        .where(Trip.version_id == version_id, Trip.shape_id == shape_id)
        .values(shape_id=None)
        .execution_options(synchronize_session="fetch")
    )
    await session.delete(shape)
    await session.commit()
