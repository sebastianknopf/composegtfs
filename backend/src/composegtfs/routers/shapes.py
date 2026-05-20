"""
Shapes endpoints.

URL: /api/versions/{version_id}/shapes
Tags: shapes
"""
from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from composegtfs.auth import get_current_user
from composegtfs.database import get_session
from composegtfs.models import Shape, ShapeIntermediatePoint, Stop, Trip, User, Version
from composegtfs.services.graphhopper import encode_polyline as _encode_polyline
from composegtfs.permissions import Permission, require

router = APIRouter(
    prefix="/api/versions/{version_id}/shapes",
    tags=["shapes"],
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


class ShapeSearchOut(BaseModel):
    """Lightweight shape representation for search/flyout endpoints."""
    version_id:      uuid.UUID
    shape_id:        str
    shape_name:      str | None
    shape_polyline:  str
    routed_polyline: str | None
    route_type:      int | None

    model_config = {"from_attributes": True}


class ShapeListOut(BaseModel):
    """Lightweight shape representation used by the list endpoint (no intermediate points)."""
    version_id:          uuid.UUID
    shape_id:            str
    shape_name:          str | None
    shape_polyline:      str
    routed_polyline:     str | None
    # Always-valid display polyline: routed_polyline if available, otherwise a
    # straight-line fallback computed at request time from intermediate points.
    # The stored shape_polyline is intentionally not used as the source of truth.
    # Default is "" for single-shape responses (POST/PATCH/GET) where the list
    # computation is not performed.
    display_polyline:    str = ""
    description:         str | None
    route_type:          int | None
    is_autoroute_active: bool

    model_config = {"from_attributes": True}


class ShapeOut(ShapeListOut):
    """Full shape representation including intermediate points."""
    intermediate_points: list[IntermediatePointOut] = []


class ShapeCreate(BaseModel):
    shape_name:          str | None = None
    description:         str | None = None
    route_type:          int | None = None
    is_autoroute_active: bool = False
    routed_polyline:     str | None = None
    intermediate_points: list[IntermediatePointIn] = []


class ShapeUpdate(BaseModel):
    shape_name:          str | None = None
    description:         str | None = None
    route_type:          int | None = None
    is_autoroute_active: bool | None = None
    # When present in the request body (even as null), the stored routed_polyline
    # is replaced. When absent, it is left unchanged.
    routed_polyline:     str | None = None
    # When provided (even as an empty list), replaces all intermediate points
    # and recomputes the shape_id. When absent (None), intermediate points and
    # shape_id are left unchanged.
    intermediate_points: list[IntermediatePointIn] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MIN_STOPS = 2
_MIN_STOPS_MSG = (
    f"At least {_MIN_STOPS} stop-based intermediate points are required."
)


def _compute_shape_id(points: list[IntermediatePointIn]) -> str:
    """
    Compute a deterministic shape_id from the ordered stop sequence.

    Mirrors the geo_pattern_hash computation for trips:
        SHA-256( "stop_id_1|stop_id_2|..." )
    where only stop-based intermediate points (stop_id is not None) contribute,
    in their given order (sort_order is assumed to be pre-applied by the caller).

    Returns a 64-character lowercase hex digest.
    Raises ValueError when fewer than 2 stop-based points are present.
    """
    stop_ids = [pt.stop_id for pt in points if pt.stop_id]
    if len(stop_ids) < _MIN_STOPS:
        raise ValueError(_MIN_STOPS_MSG)
    return hashlib.sha256("|".join(stop_ids).encode()).hexdigest()



async def _compute_straight_polyline(
    version_id: uuid.UUID,
    points: list[IntermediatePointIn],
    session: AsyncSession,
) -> str:
    """
    Build a straight-line shape_polyline from intermediate points.
    Stop-based points have their coordinates looked up from the stops table.
    Coordinate-based points use lat/lon directly.
    Returns a Google Encoded Polyline string (empty if fewer than 2 valid coords).
    """
    stop_ids = [pt.stop_id for pt in points if pt.stop_id]
    stops_by_id: dict[str, Stop] = {}
    if stop_ids:
        rows = (await session.execute(
            select(Stop).where(
                Stop.version_id == version_id,
                Stop.stop_id.in_(stop_ids),
            )
        )).scalars().all()
        stops_by_id = {s.stop_id: s for s in rows}

    coords: list[tuple[float, float]] = []
    for pt in points:
        if pt.stop_id:
            s = stops_by_id.get(pt.stop_id)
            if s and s.stop_lat is not None and s.stop_lon is not None:
                coords.append((s.stop_lat, s.stop_lon))
        elif pt.lat is not None and pt.lon is not None:
            coords.append((pt.lat, pt.lon))

    return _encode_polyline(coords) if len(coords) >= 2 else ""


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
    summary="List all shapes in a version",
    dependencies=[require(Permission.SHAPES_READ)],
)
async def list_shapes(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ShapeListOut]:
    await _get_version_or_404(version_id, session)
    shapes = list((await session.execute(
        select(Shape)
        .where(Shape.version_id == version_id)
        .options(selectinload(Shape.intermediate_points))
        .order_by(Shape.shape_name.nulls_last(), Shape.shape_id)
    )).scalars().all())

    # Batch-load all stops that are referenced by shapes without a routed_polyline,
    # so we can compute straight-line fallback polylines without N+1 queries.
    stop_ids_needed: set[str] = {
        pt.stop_id
        for shape in shapes
        if not shape.routed_polyline
        for pt in shape.intermediate_points
        if pt.stop_id
    }
    stops_by_id: dict[str, Stop] = {}
    if stop_ids_needed:
        stops_by_id = {
            s.stop_id: s
            for s in (await session.execute(
                select(Stop).where(
                    Stop.version_id == version_id,
                    Stop.stop_id.in_(stop_ids_needed),
                )
            )).scalars().all()
        }

    out: list[ShapeListOut] = []
    for shape in shapes:
        display_polyline = shape.routed_polyline or ""
        if not display_polyline:
            coords: list[tuple[float, float]] = []
            for pt in sorted(shape.intermediate_points, key=lambda p: p.sort_order):
                if pt.stop_id:
                    s = stops_by_id.get(pt.stop_id)
                    if s and s.stop_lat is not None and s.stop_lon is not None:
                        coords.append((s.stop_lat, s.stop_lon))
                elif pt.lat is not None and pt.lon is not None:
                    coords.append((pt.lat, pt.lon))
            display_polyline = _encode_polyline(coords) if len(coords) >= 2 else ""

        out.append(ShapeListOut(
            version_id=shape.version_id,
            shape_id=shape.shape_id,
            shape_name=shape.shape_name,
            shape_polyline=shape.shape_polyline,
            routed_polyline=shape.routed_polyline,
            display_polyline=display_polyline,
            description=shape.description,
            route_type=shape.route_type,
            is_autoroute_active=shape.is_autoroute_active,
        ))
    return out


@router.post(
    "",
    response_model=ShapeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new shape",
    dependencies=[require(Permission.SHAPES_WRITE)],
)
async def create_shape(
    version_id: uuid.UUID,
    body: ShapeCreate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Shape:
    await _get_version_or_404(version_id, session)

    try:
        shape_id = _compute_shape_id(body.intermediate_points)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    # Prevent duplicate: same stop sequence already exists in this version
    existing = (await session.execute(
        select(Shape).where(
            Shape.version_id == version_id,
            Shape.shape_id == shape_id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A shape with an identical stop sequence already exists in this version.",
        )

    shape_polyline = await _compute_straight_polyline(version_id, body.intermediate_points, session)
    shape = Shape(
        version_id=version_id,
        shape_id=shape_id,
        shape_name=body.shape_name.strip() if body.shape_name else None,
        shape_polyline=shape_polyline,
        routed_polyline=body.routed_polyline,
        description=body.description.strip() if body.description else None,
        route_type=body.route_type,
        is_autoroute_active=body.is_autoroute_active,
    )
    session.add(shape)
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
    return await _get_shape_or_404(version_id, shape_id, session, with_points=True)


@router.get(
    "/search",
    response_model=list[ShapeSearchOut],
    summary="Search shapes by name or ID (lightweight, for flyouts)",
    dependencies=[require(Permission.SHAPES_READ)],
)
async def search_shapes(
    version_id: uuid.UUID,
    q: str | None = Query(default=None, description="Search by shape_id or shape_name"),
    limit: int = Query(default=50, ge=1, le=500),
    route_type: int | None = Query(default=None, description="Filter by route_type"),
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Shape]:
    await _get_version_or_404(version_id, session)
    stmt = select(Shape).where(Shape.version_id == version_id)
    query = (q or "").strip()
    if query:
        like = f"%{query}%"
        stmt = stmt.where(
            or_(
                Shape.shape_id.ilike(like),
                Shape.shape_name.ilike(like),
            )
        )
    if route_type is not None:
        stmt = stmt.where(Shape.route_type == route_type)
    stmt = stmt.order_by(Shape.shape_name.nulls_last(), Shape.shape_id).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get(
    "/{shape_id}",
    response_model=ShapeOut,
    summary="Get a single shape including its intermediate points",
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
    summary="Update metadata and/or intermediate points of a shape",
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

    effective_shape_id = shape_id

    if body.intermediate_points is not None:
        # Validate minimum stop count and compute new shape_id
        try:
            new_shape_id = _compute_shape_id(body.intermediate_points)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )

        if new_shape_id != shape_id:
            # Check for collision with another existing shape
            collision = (await session.execute(
                select(Shape).where(
                    Shape.version_id == version_id,
                    Shape.shape_id == new_shape_id,
                )
            )).scalar_one_or_none()
            if collision is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A shape with an identical stop sequence already exists in this version.",
                )

            # Collect all new field values for a single Core UPDATE statement
            new_values: dict = {"shape_id": new_shape_id}
            new_values["shape_polyline"] = await _compute_straight_polyline(version_id, body.intermediate_points, session)
            if "routed_polyline" in body.model_fields_set:
                new_values["routed_polyline"] = body.routed_polyline
            if body.shape_name is not None:
                new_values["shape_name"] = body.shape_name.strip() or None
            if body.description is not None:
                new_values["description"] = body.description.strip() or None
            if body.route_type is not None:
                new_values["route_type"] = body.route_type
            if body.is_autoroute_active is not None:
                new_values["is_autoroute_active"] = body.is_autoroute_active

            # 1. Delete old intermediate points (removes FK dependency before PK rename)
            await session.execute(
                delete(ShapeIntermediatePoint)
                .where(
                    ShapeIntermediatePoint.version_id == version_id,
                    ShapeIntermediatePoint.shape_id == shape_id,
                )
                .execution_options(synchronize_session=False)
            )
            # 2. Rename the shape PK (+ apply any scalar changes in the same statement)
            await session.execute(
                update(Shape)
                .where(Shape.version_id == version_id, Shape.shape_id == shape_id)
                .values(**new_values)
                .execution_options(synchronize_session=False)
            )
            # 3. Redirect trip references to the new shape_id
            await session.execute(
                update(Trip)
                .where(Trip.version_id == version_id, Trip.shape_id == shape_id)
                .values(shape_id=new_shape_id)
                .execution_options(synchronize_session=False)
            )
            effective_shape_id = new_shape_id
            # Expunge the stale ORM object so the session doesn't try to flush it
            session.expunge(shape)

        else:
            # Same shape_id: apply scalar changes via ORM, replace points below
            if body.shape_name is not None:
                shape.shape_name = body.shape_name.strip() or None
            if body.description is not None:
                shape.description = body.description.strip() or None
            if body.route_type is not None:
                shape.route_type = body.route_type
            if body.is_autoroute_active is not None:
                shape.is_autoroute_active = body.is_autoroute_active
            if "routed_polyline" in body.model_fields_set:
                shape.routed_polyline = body.routed_polyline
            shape.shape_polyline = await _compute_straight_polyline(version_id, body.intermediate_points, session)

            # Delete old intermediate points
            await session.execute(
                delete(ShapeIntermediatePoint)
                .where(
                    ShapeIntermediatePoint.version_id == version_id,
                    ShapeIntermediatePoint.shape_id == shape_id,
                )
                .execution_options(synchronize_session=False)
            )

        # Insert new intermediate points (applies for both same/changed shape_id)
        for pt in body.intermediate_points:
            session.add(ShapeIntermediatePoint(
                version_id=version_id,
                shape_id=effective_shape_id,
                sort_order=pt.sort_order,
                lat=pt.lat,
                lon=pt.lon,
                stop_id=pt.stop_id or None,
            ))

    else:
        # No intermediate_points provided → only scalar field changes
        if body.shape_name is not None:
            shape.shape_name = body.shape_name.strip() or None
        if body.description is not None:
            shape.description = body.description.strip() or None
        if body.route_type is not None:
            shape.route_type = body.route_type
        if body.is_autoroute_active is not None:
            shape.is_autoroute_active = body.is_autoroute_active
        if "routed_polyline" in body.model_fields_set:
            shape.routed_polyline = body.routed_polyline

    await session.commit()
    return await _get_shape_or_404(version_id, effective_shape_id, session, with_points=True)


@router.delete(
    "/{shape_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a shape and detach it from trips",
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
