from __future__ import annotations

import hashlib
import secrets
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import Calendar, Route, RouteBandStop, Shape, Stop, StopTime, Trip, User, Version
from app.permissions import Permission, require

router = APIRouter(prefix="/api/versions/{version_id}/schedule", tags=["schedule"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_version_or_404(version_id: uuid.UUID, session: AsyncSession) -> Version:
    result = await session.execute(select(Version).where(Version.id == version_id))
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return version


async def _get_route_or_404(version_id: uuid.UUID, route_id: str, session: AsyncSession) -> Route:
    result = await session.execute(
        select(Route).where(Route.version_id == version_id, Route.route_id == route_id)
    )
    route = result.scalar_one_or_none()
    if route is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")
    return route


async def _get_stop_or_404(version_id: uuid.UUID, stop_id: str, session: AsyncSession) -> Stop:
    result = await session.execute(
        select(Stop).where(Stop.version_id == version_id, Stop.stop_id == stop_id)
    )
    stop = result.scalar_one_or_none()
    if stop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stop not found")
    return stop


async def _get_shape_or_404(version_id: uuid.UUID, shape_id: str, session: AsyncSession) -> Shape:
    result = await session.execute(
        select(Shape).where(Shape.version_id == version_id, Shape.shape_id == shape_id)
    )
    shape = result.scalar_one_or_none()
    if shape is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shape not found")
    return shape


# ---------------------------------------------------------------------------
# Trip hash helpers
# ---------------------------------------------------------------------------

def _time_to_seconds(t: str | None) -> int | None:
    """Convert 'H:MM' or 'H:MM:SS' to total seconds. Returns None for invalid/missing input."""
    if t is None:
        return None
    parts = t.strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 3600 + int(parts[1]) * 60
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except (ValueError, IndexError):
        return None
    return None


async def _compute_trip_hashes(
    version_id: uuid.UUID,
    trip_id: str,
    session: AsyncSession,
) -> tuple[str | None, str | None]:
    """
    Compute geo_pattern_hash and schedule_pattern_hash for a trip.

    geo_pattern_hash
    ----------------
    Ordered list of stop_ids for all stop times that have a departure_time,
    sorted by route_band_stop.sort_order (no band-specific sequence numbers).
    Hash input:  "stop_a|stop_b|stop_c|..."

    schedule_pattern_hash
    ---------------------
    For each such stop time in order, one segment:
            "<stop_id>;<dwell_secs>;<run_secs_to_next_arrival>;<pickup_type>;"
            "<drop_off_type>;<continuous_pickup>;<continuous_drop_off>;<timepoint>"
        where:
            - dwell_secs = departure - arrival (or 0 if arrival is missing, i.e. same as departure)
            - run_secs_to_next_arrival = next_arrival_or_departure - this_departure
                (empty string for the last stop)
        This intentionally excludes absolute clock times so trips with identical
        relative timing profiles produce the same hash. No band-sequence data involved.
    Hash input:  "<seg_0>|<seg_1>|..."

    Returns (None, None) when the trip has no stop times with departure_time set.
    """
    rows = (
        await session.execute(
            select(StopTime, RouteBandStop)
            .join(RouteBandStop, StopTime.route_band_stop_id == RouteBandStop.id)
            .where(
                StopTime.version_id == version_id,
                StopTime.trip_id == trip_id,
                StopTime.departure_time.isnot(None),
            )
            .order_by(RouteBandStop.sort_order)
        )
    ).all()

    if not rows:
        return None, None

    # geo_pattern_hash -------------------------------------------------------
    stop_ids = [rbs.stop_id for _, rbs in rows]
    geo_hash = hashlib.sha256("|".join(stop_ids).encode()).hexdigest()

    # schedule_pattern_hash --------------------------------------------------
    # Use only relative timing profile (dwell + run times), no absolute times.
    parts: list[str] = []
    for i, (st, rbs) in enumerate(rows):
        dep_secs = _time_to_seconds(st.departure_time)
        arr_secs = _time_to_seconds(st.arrival_time or st.departure_time)

        dwell: int | str = (
            (dep_secs - arr_secs)
            if dep_secs is not None and arr_secs is not None
            else ""
        )

        if i < len(rows) - 1:
            next_st, _ = rows[i + 1]
            next_arr = next_st.arrival_time or next_st.departure_time
            next_secs = _time_to_seconds(next_arr)
            run: int | str = (
                (next_secs - dep_secs)
                if dep_secs is not None and next_secs is not None
                else ""
            )
        else:
            run = ""

        parts.append(";".join([
            rbs.stop_id,
            str(dwell),
            str(run),
            "" if st.pickup_type         is None else str(st.pickup_type),
            "" if st.drop_off_type       is None else str(st.drop_off_type),
            "" if st.continuous_pickup   is None else str(st.continuous_pickup),
            "" if st.continuous_drop_off is None else str(st.continuous_drop_off),
            "" if st.timepoint           is None else str(st.timepoint),
        ]))

    sched_hash = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return geo_hash, sched_hash


async def _refresh_trip_hashes(
    version_id: uuid.UUID,
    trip_id: str,
    session: AsyncSession,
) -> None:
    """Recompute and persist both pattern hashes for the given trip.

    Must be called *after* session.flush() and *before* session.commit() so
    that any pending stop-time changes are visible to the SELECT inside
    _compute_trip_hashes.
    """
    geo_hash, sched_hash = await _compute_trip_hashes(version_id, trip_id, session)
    await session.execute(
        update(Trip)
        .where(Trip.version_id == version_id, Trip.trip_id == trip_id)
        .values(geo_pattern_hash=geo_hash, schedule_pattern_hash=sched_hash)
        .execution_options(synchronize_session="fetch")
    )


async def _refresh_hashes_for_route_direction(
    version_id: uuid.UUID,
    route_id: str,
    direction: int,
    session: AsyncSession,
) -> None:
    """Recompute hashes for all trips of a route+direction.

    Needed when route band entries are added/reordered/removed, because the
    stop order/availability can change without directly touching a StopTime row.
    """
    trip_ids = (
        await session.execute(
            select(Trip.trip_id)
            .where(
                Trip.version_id == version_id,
                Trip.route_id == route_id,
                Trip.direction_id == direction,
            )
        )
    ).scalars().all()
    for trip_id in trip_ids:
        await _refresh_trip_hashes(version_id, trip_id, session)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DayTypeOut(BaseModel):
    service_id: str
    name:       str | None

    model_config = {"from_attributes": True}


class ScheduleRouteOut(BaseModel):
    route_id:         str
    route_short_name: str | None
    route_long_name:  str | None
    route_color:      str | None
    route_text_color: str | None
    route_sort_order: int | None
    route_type:       int

    model_config = {"from_attributes": True}


class SchedulePlatformOut(BaseModel):
    stop_id:       str
    stop_name:     str | None
    platform_code: str | None
    stop_lat:      float | None
    stop_lon:      float | None

    model_config = {"from_attributes": True}


class RouteBandStopOut(BaseModel):
    id:         uuid.UUID
    version_id: uuid.UUID
    route_id:   str
    direction:  int
    stop_id:    str
    sort_order: int

    model_config = {"from_attributes": True}


class RouteBandStopAdd(BaseModel):
    stop_id:    str
    sort_order: int | None = None  # if omitted, appended at end

    @field_validator("stop_id")
    @classmethod
    def stop_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("stop_id must not be empty")
        return v


class RouteBandStopReorder(BaseModel):
    sort_order: int

    @field_validator("sort_order")
    @classmethod
    def sort_order_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("sort_order must be non-negative")
        return v


# ---------------------------------------------------------------------------
# Route / platform lookup endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/routes",
    response_model=list[ScheduleRouteOut],
    summary="List routes for schedule view (name and colour only)",
    dependencies=[require(Permission.SCHEDULE_READ)],
)
async def list_schedule_routes(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Route]:
    await _get_version_or_404(version_id, session)
    result = await session.execute(
        select(Route)
        .where(Route.version_id == version_id)
        .order_by(Route.route_sort_order.nulls_last(), Route.route_id)
    )
    return list(result.scalars().all())


@router.get(
    "/day-types",
    response_model=list[DayTypeOut],
    summary="List service IDs (Tagesarten) available in this version",
    dependencies=[require(Permission.SCHEDULE_READ)],
)
async def list_schedule_day_types(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Calendar]:
    await _get_version_or_404(version_id, session)
    result = await session.execute(
        select(Calendar)
        .where(Calendar.version_id == version_id)
        .order_by(Calendar.service_id)
    )
    return list(result.scalars().all())


@router.get(
    "/platforms",
    response_model=list[SchedulePlatformOut],
    summary="List all platforms (Steige) for schedule view",
    dependencies=[require(Permission.SCHEDULE_READ)],
)
async def list_schedule_platforms(
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


# ---------------------------------------------------------------------------
# Route band endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/{route_id}/band/{direction}",
    response_model=list[RouteBandStopOut],
    summary="Get ordered stop list (Linienband) for a route/direction",
    dependencies=[require(Permission.SCHEDULE_READ)],
)
async def get_route_band(
    version_id: uuid.UUID,
    route_id: str,
    direction: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[RouteBandStop]:
    await _get_version_or_404(version_id, session)
    await _get_route_or_404(version_id, route_id, session)
    if direction not in (0, 1):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="direction must be 0 (outbound) or 1 (inbound)")
    result = await session.execute(
        select(RouteBandStop)
        .where(
            RouteBandStop.version_id == version_id,
            RouteBandStop.route_id == route_id,
            RouteBandStop.direction == direction,
        )
        .order_by(RouteBandStop.sort_order)
    )
    return list(result.scalars().all())


@router.post(
    "/{route_id}/band/{direction}",
    response_model=RouteBandStopOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a stop to a route band (may appear multiple times)",
    dependencies=[require(Permission.SCHEDULE_WRITE)],
)
async def add_route_band_stop(
    version_id: uuid.UUID,
    route_id: str,
    direction: int,
    body: RouteBandStopAdd,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RouteBandStop:
    await _get_version_or_404(version_id, session)
    await _get_route_or_404(version_id, route_id, session)
    await _get_stop_or_404(version_id, body.stop_id, session)

    if direction not in (0, 1):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="direction must be 0 (outbound) or 1 (inbound)")

    # Determine sort_order
    if body.sort_order is not None:
        sort_order = body.sort_order
        # Ensure the requested position is not already taken
        clash = await session.execute(
            select(RouteBandStop).where(
                RouteBandStop.version_id == version_id,
                RouteBandStop.route_id == route_id,
                RouteBandStop.direction == direction,
                RouteBandStop.sort_order == sort_order,
            )
        )
        if clash.scalar_one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="sort_order position is already occupied in this route band")
    else:
        max_result = await session.execute(
            select(RouteBandStop.sort_order)
            .where(
                RouteBandStop.version_id == version_id,
                RouteBandStop.route_id == route_id,
                RouteBandStop.direction == direction,
            )
            .order_by(RouteBandStop.sort_order.desc())
            .limit(1)
        )
        max_order = max_result.scalar_one_or_none()
        sort_order = (max_order + 1) if max_order is not None else 0

    entry = RouteBandStop(
        version_id=version_id,
        route_id=route_id,
        direction=direction,
        stop_id=body.stop_id,
        sort_order=sort_order,
    )
    session.add(entry)
    await session.flush()
    await _refresh_hashes_for_route_direction(version_id, route_id, direction, session)
    await session.commit()
    await session.refresh(entry)
    return entry


@router.put(
    "/{route_id}/band/{direction}/{entry_id}",
    response_model=RouteBandStopOut,
    summary="Update sort_order of a route band entry (identified by its UUID)",
    dependencies=[require(Permission.SCHEDULE_WRITE)],
)
async def reorder_route_band_stop(
    version_id: uuid.UUID,
    route_id: str,
    direction: int,
    entry_id: uuid.UUID,
    body: RouteBandStopReorder,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RouteBandStop:
    if direction not in (0, 1):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="direction must be 0 (outbound) or 1 (inbound)")
    result = await session.execute(
        select(RouteBandStop).where(
            RouteBandStop.id == entry_id,
            RouteBandStop.version_id == version_id,
            RouteBandStop.route_id == route_id,
            RouteBandStop.direction == direction,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Route band entry not found")

    # Ensure the target position is not already taken by another entry
    if entry.sort_order != body.sort_order:
        clash = await session.execute(
            select(RouteBandStop).where(
                RouteBandStop.version_id == version_id,
                RouteBandStop.route_id == route_id,
                RouteBandStop.direction == direction,
                RouteBandStop.sort_order == body.sort_order,
            )
        )
        if clash.scalar_one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="sort_order position is already occupied in this route band")

    entry.sort_order = body.sort_order
    await session.flush()
    await _refresh_hashes_for_route_direction(version_id, route_id, direction, session)
    await session.commit()
    await session.refresh(entry)
    return entry


@router.delete(
    "/{route_id}/band/{direction}/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a route band entry (identified by its UUID)",
    dependencies=[require(Permission.SCHEDULE_WRITE)],
)
async def remove_route_band_stop(
    version_id: uuid.UUID,
    route_id: str,
    direction: int,
    entry_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    if direction not in (0, 1):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="direction must be 0 (outbound) or 1 (inbound)")
    result = await session.execute(
        select(RouteBandStop).where(
            RouteBandStop.id == entry_id,
            RouteBandStop.version_id == version_id,
            RouteBandStop.route_id == route_id,
            RouteBandStop.direction == direction,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Route band entry not found")
    deleted_sort_order = entry.sort_order
    await session.delete(entry)
    await session.flush()   # execute DELETE before the UPDATE below

    # Decrement sort_order for all subsequent entries in this band so the
    # sequence stays contiguous.  After the flush above the slot at
    # deleted_sort_order is free, so the single UPDATE never hits a
    # unique-constraint violation.
    await session.execute(
        update(RouteBandStop)
        .where(
            RouteBandStop.version_id == version_id,
            RouteBandStop.route_id   == route_id,
            RouteBandStop.direction  == direction,
            RouteBandStop.sort_order >  deleted_sort_order,
        )
        .values(sort_order=RouteBandStop.sort_order - 1)
        .execution_options(synchronize_session="fetch")
    )
    await session.flush()
    await _refresh_hashes_for_route_direction(version_id, route_id, direction, session)
    await session.commit()


# ===========================================================================
# Shapes
# ===========================================================================

class ShapeOut(BaseModel):
    version_id:      uuid.UUID
    shape_id:        str
    shape_name:      str | None
    shape_polyline:  str
    routed_polyline: str | None
    route_type:      int | None

    model_config = {"from_attributes": True}


@router.get(
    "/shapes",
    response_model=list[ShapeOut],
    summary="Search shapes for route-path flyouts",
    dependencies=[require(Permission.SCHEDULE_READ)],
)
async def search_shapes(
    version_id: uuid.UUID,
    q: str | None = Query(default=None, description="Search by shape_id or shape_name"),
    limit: int = Query(default=50, ge=1, le=500),
    route_type: int | None = Query(default=None, description="Filter by shape route_type"),
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


# ===========================================================================
# Trips
# ===========================================================================

async def _get_trip_or_404(
    version_id: uuid.UUID,
    route_id:   str,
    trip_id:    str,
    session:    AsyncSession,
) -> Trip:
    result = await session.execute(
        select(Trip).where(
            Trip.version_id == version_id,
            Trip.route_id   == route_id,
            Trip.trip_id    == trip_id,
        )
    )
    trip = result.scalar_one_or_none()
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return trip


# ---- Schemas ---------------------------------------------------------------

class TripOut(BaseModel):
    version_id:            uuid.UUID
    trip_id:               str
    route_id:              str
    service_id:            str | None
    direction_id:          int | None
    trip_short_name:       str | None
    trip_headsign_id:      str | None
    block_id:              str | None
    shape_id:              str | None
    wheelchair_accessible: int | None
    bikes_allowed:         int | None
    cars_allowed:          int | None
    geo_pattern_hash:      str | None
    schedule_pattern_hash: str | None

    model_config = {"from_attributes": True}


class TripCreate(BaseModel):
    trip_id:               str | None = None  # auto-generated if omitted
    service_id:            str | None = None
    direction_id:          int | None = None
    trip_short_name:       str | None = None
    trip_headsign_id:      str | None = None
    block_id:              str | None = None
    shape_id:              str | None = None
    wheelchair_accessible: int | None = None
    bikes_allowed:         int | None = None
    cars_allowed:          int | None = None

    @field_validator("direction_id")
    @classmethod
    def validate_direction(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1):
            raise ValueError("direction_id must be 0 or 1")
        return v


class TripUpdate(BaseModel):
    service_id:            str | None = None
    direction_id:          int | None = None
    trip_short_name:       str | None = None
    trip_headsign_id:      str | None = None
    block_id:              str | None = None
    shape_id:              str | None = None
    wheelchair_accessible: int | None = None
    bikes_allowed:         int | None = None
    cars_allowed:          int | None = None

    @field_validator("direction_id")
    @classmethod
    def validate_direction(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1):
            raise ValueError("direction_id must be 0 or 1")
        return v


class EmbeddedStopTimeOut(BaseModel):
    """Stop time embedded inside a TripWithStopTimesOut response.

    Omits version_id and trip_id (redundant in this context).
    """
    route_band_stop_id:  uuid.UUID
    arrival_time:        str | None
    departure_time:      str | None
    stop_headsign_id:    str | None
    pickup_type:         int | None
    drop_off_type:       int | None
    continuous_pickup:   int | None
    continuous_drop_off: int | None
    shape_dist_traveled: float | None
    timepoint:           int | None

    model_config = {"from_attributes": True}


class TripWithStopTimesOut(TripOut):
    """Trip including all its stop times, returned by the list endpoint."""
    stop_times: list[EmbeddedStopTimeOut] = []


# ---- Endpoints -------------------------------------------------------------

@router.get(
    "/{route_id}/trips",
    response_model=list[TripWithStopTimesOut],
    summary="List trips for a route (optionally filter by direction) including embedded stop times",
    dependencies=[require(Permission.SCHEDULE_READ)],
)
async def list_trips(
    version_id:  uuid.UUID,
    route_id:    str,
    direction:   int | None = Query(default=None, description="0 = outbound, 1 = inbound"),
    _:           User          = Depends(get_current_user),
    session:     AsyncSession  = Depends(get_session),
) -> list[TripWithStopTimesOut]:
    await _get_version_or_404(version_id, session)
    await _get_route_or_404(version_id, route_id, session)

    stmt = (
        select(Trip)
        .where(Trip.version_id == version_id, Trip.route_id == route_id)
    )
    if direction is not None:
        if direction not in (0, 1):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="direction must be 0 or 1")
        stmt = stmt.where(Trip.direction_id == direction)
    stmt = stmt.order_by(Trip.trip_id)

    result = await session.execute(stmt)
    trips = list(result.scalars().all())

    # Bulk-load all stop times for the returned trips in a single query.
    stop_times_by_trip: dict[str, list[StopTime]] = {}
    if trips:
        trip_ids = [t.trip_id for t in trips]
        st_result = await session.execute(
            select(StopTime)
            .where(
                StopTime.version_id == version_id,
                StopTime.trip_id.in_(trip_ids),
            )
            .join(StopTime.route_band_stop)
            .order_by(RouteBandStop.sort_order)
        )
        for st in st_result.scalars().all():
            stop_times_by_trip.setdefault(st.trip_id, []).append(st)

    return [
        TripWithStopTimesOut(
            **TripOut.model_validate(trip).model_dump(),
            stop_times=[
                EmbeddedStopTimeOut.model_validate(st)
                for st in stop_times_by_trip.get(trip.trip_id, [])
            ],
        )
        for trip in trips
    ]


@router.get(
    "/{route_id}/trips/{trip_id}",
    response_model=TripOut,
    summary="Get a single trip by ID",
    dependencies=[require(Permission.SCHEDULE_READ)],
)
async def get_trip(
    version_id: uuid.UUID,
    route_id:   str,
    trip_id:    str,
    _:          User          = Depends(get_current_user),
    session:    AsyncSession  = Depends(get_session),
) -> Trip:
    await _get_version_or_404(version_id, session)
    return await _get_trip_or_404(version_id, route_id, trip_id, session)


@router.post(
    "/{route_id}/trips",
    response_model=TripOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new trip for a route",
    dependencies=[require(Permission.SCHEDULE_WRITE)],
)
async def create_trip(
    version_id: uuid.UUID,
    route_id:   str,
    body:       TripCreate,
    _:          User          = Depends(get_current_user),
    session:    AsyncSession  = Depends(get_session),
) -> Trip:
    await _get_version_or_404(version_id, session)
    await _get_route_or_404(version_id, route_id, session)

    shape_id = (body.shape_id or "").strip() or None
    if body.shape_id is not None and shape_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="shape_id must not be empty")
    if shape_id is not None:
        await _get_shape_or_404(version_id, shape_id, session)

    trip_id = (body.trip_id or str(uuid.uuid4())).strip()
    if not trip_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="trip_id must not be empty")

    # Uniqueness check within version
    clash = await session.execute(
        select(Trip).where(Trip.version_id == version_id, Trip.trip_id == trip_id)
    )
    if clash.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="A trip with this trip_id already exists in this version")

    trip = Trip(
        version_id=version_id,
        trip_id=trip_id,
        route_id=route_id,
        service_id=body.service_id,
        direction_id=body.direction_id,
        trip_short_name=body.trip_short_name,
        trip_headsign_id=body.trip_headsign_id,
        block_id=body.block_id,
        shape_id=shape_id,
        wheelchair_accessible=body.wheelchair_accessible,
        bikes_allowed=body.bikes_allowed,
        cars_allowed=body.cars_allowed,
    )
    session.add(trip)
    await session.flush()
    await _refresh_trip_hashes(version_id, trip.trip_id, session)
    await session.commit()
    await session.refresh(trip)
    return trip


@router.put(
    "/{route_id}/trips/{trip_id}",
    response_model=TripOut,
    summary="Update an existing trip",
    dependencies=[require(Permission.SCHEDULE_WRITE)],
)
async def update_trip(
    version_id: uuid.UUID,
    route_id:   str,
    trip_id:    str,
    body:       TripUpdate,
    _:          User          = Depends(get_current_user),
    session:    AsyncSession  = Depends(get_session),
) -> Trip:
    await _get_version_or_404(version_id, session)
    trip = await _get_trip_or_404(version_id, route_id, trip_id, session)

    updates = body.model_dump(exclude_unset=True)
    if "shape_id" in updates:
        raw_shape_id = updates["shape_id"]
        normalized_shape_id = (raw_shape_id or "").strip() or None
        if raw_shape_id is not None and normalized_shape_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="shape_id must not be empty")
        if normalized_shape_id is not None:
            await _get_shape_or_404(version_id, normalized_shape_id, session)
        updates["shape_id"] = normalized_shape_id

    for field, value in updates.items():
        setattr(trip, field, value)

    await session.flush()
    await _refresh_trip_hashes(version_id, trip_id, session)
    await session.commit()
    await session.refresh(trip)
    return trip


@router.delete(
    "/{route_id}/trips/{trip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a trip (and all its stop times)",
    dependencies=[require(Permission.SCHEDULE_DELETE)],
)
async def delete_trip(
    version_id: uuid.UUID,
    route_id:   str,
    trip_id:    str,
    _:          User          = Depends(get_current_user),
    session:    AsyncSession  = Depends(get_session),
) -> None:
    await _get_version_or_404(version_id, session)
    trip = await _get_trip_or_404(version_id, route_id, trip_id, session)
    await session.delete(trip)
    await session.commit()


class TripBatchDeleteRequest(BaseModel):
    trip_ids: list[str]


# ---------------------------------------------------------------------------
# Batch-Shift helper
# ---------------------------------------------------------------------------

def _seconds_to_gtfs_time(secs: int) -> str:
    """Convert total seconds (>= 0) to GTFS HH:MM:SS format. Hours are zero-padded and may exceed 23."""
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


class TripBatchShiftRequest(BaseModel):
    trip_ids:       list[str]
    offset_minutes: int   # 1..1439
    direction:      str   # "forward" | "backward"

    @field_validator("offset_minutes")
    @classmethod
    def validate_offset(cls, v: int) -> int:
        if v < 1 or v > 1439:
            raise ValueError("offset_minutes must be between 1 and 1439")
        return v

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        if v not in ("forward", "backward"):
            raise ValueError("direction must be 'forward' or 'backward'")
        return v


@router.post(
    "/{route_id}/trips/batch-shift",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Shift departure/arrival times of multiple trips by a fixed offset",
    dependencies=[require(Permission.SCHEDULE_WRITE)],
)
async def batch_shift_trips(
    version_id: uuid.UUID,
    route_id:   str,
    req:        TripBatchShiftRequest = Body(...),
    _:          User                  = Depends(get_current_user),
    session:    AsyncSession          = Depends(get_session),
) -> None:
    await _get_version_or_404(version_id, session)
    offset_secs = req.offset_minutes * 60
    if req.direction == "backward":
        offset_secs = -offset_secs

    # Load all stop times for the affected trips in one query
    result = await session.execute(
        select(StopTime).where(
            StopTime.version_id == version_id,
            StopTime.trip_id.in_(req.trip_ids),
        )
    )
    stop_times = result.scalars().all()

    for st in stop_times:
        for attr in ("arrival_time", "departure_time"):
            old_val: str | None = getattr(st, attr)
            if old_val is None:
                continue
            old_secs = _time_to_seconds(old_val)
            if old_secs is None:
                continue
            new_secs = old_secs + offset_secs
            if new_secs < 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Shift would produce a negative time for trip '{st.trip_id}'. "
                           "Reduce the offset or choose 'forward' direction.",
                )
            setattr(st, attr, _seconds_to_gtfs_time(new_secs))

    await session.flush()
    # Refresh hashes for all affected trips
    for trip_id in req.trip_ids:
        await _refresh_trip_hashes(version_id, trip_id, session)
    await session.commit()


@router.post(
    "/{route_id}/trips/batch-delete",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete multiple trips (and all their stop times)",
    dependencies=[require(Permission.SCHEDULE_DELETE)],
)
async def batch_delete_trips(
    version_id: uuid.UUID,
    route_id:   str,
    req:        TripBatchDeleteRequest = Body(...),
    _:          User                   = Depends(get_current_user),
    session:    AsyncSession           = Depends(get_session),
) -> None:
    await _get_version_or_404(version_id, session)
    result = await session.execute(
        select(Trip).where(
            Trip.version_id == version_id,
            Trip.route_id   == route_id,
            Trip.trip_id.in_(req.trip_ids),
        )
    )
    for trip in result.scalars().all():
        await session.delete(trip)
    await session.commit()


# ---------------------------------------------------------------------------
# Batch-Copy
# ---------------------------------------------------------------------------

class TripBatchCopyShift(BaseModel):
    offset_minutes: int   # 1..1439
    direction:      str   # "forward" | "backward"

    @field_validator("offset_minutes")
    @classmethod
    def validate_offset(cls, v: int) -> int:
        if v < 1 or v > 1439:
            raise ValueError("offset_minutes must be between 1 and 1439")
        return v

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        if v not in ("forward", "backward"):
            raise ValueError("direction must be 'forward' or 'backward'")
        return v


class TripBatchCopyHeadway(BaseModel):
    start_time:      str   # GTFS H:MM or H:MM:SS
    end_time:        str   # GTFS H:MM or H:MM:SS
    headway_minutes: int   # 1..1439

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def validate_time(cls, v: str) -> str:
        import re
        if not re.fullmatch(r"\d+:\d{2}(:\d{2})?", v.strip()):
            raise ValueError("Time must be in H:MM or H:MM:SS format")
        return v.strip()

    @field_validator("headway_minutes")
    @classmethod
    def validate_headway(cls, v: int) -> int:
        if v < 1 or v > 1439:
            raise ValueError("headway_minutes must be between 1 and 1439")
        return v


class TripBatchCopyRequest(BaseModel):
    trip_ids:          list[str]
    mode:              str                      # "shift" | "headway"
    shift:             TripBatchCopyShift  | None = None
    headway:           TripBatchCopyHeadway | None = None
    short_name_start:  str | None = None        # optional running short name start (string to preserve leading zeros)
    short_name_step:   int = 1                  # step between short names (default 1)

    @field_validator("short_name_start")
    @classmethod
    def validate_short_name_start(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.lstrip('-')
        if not stripped.isdigit():
            raise ValueError("short_name_start must be an integer string")
        return v
    service_id:        str | None = None        # optional day-type override

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("shift", "headway"):
            raise ValueError("mode must be 'shift' or 'headway'")
        return v


@router.post(
    "/{route_id}/trips/batch-copy",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Copy multiple trips with optional time shift or headway generation",
    dependencies=[require(Permission.SCHEDULE_WRITE)],
)
async def batch_copy_trips(
    version_id: uuid.UUID,
    route_id:   str,
    req:        TripBatchCopyRequest = Body(...),
    _:          User                 = Depends(get_current_user),
    session:    AsyncSession         = Depends(get_session),
) -> None:
    await _get_version_or_404(version_id, session)

    if req.mode == "shift":
        if req.shift is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="shift parameters are required for mode='shift'")
    else:  # headway
        if req.headway is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="headway parameters are required for mode='headway'")

    # Load source trips
    trips_result = await session.execute(
        select(Trip).where(
            Trip.version_id == version_id,
            Trip.route_id   == route_id,
            Trip.trip_id.in_(req.trip_ids),
        )
    )
    source_trips: list[Trip] = list(trips_result.scalars().all())
    if not source_trips:
        return

    # Load all stop times for source trips in one query
    st_result = await session.execute(
        select(StopTime)
        .where(
            StopTime.version_id == version_id,
            StopTime.trip_id.in_(req.trip_ids),
        )
        .join(StopTime.route_band_stop)
        .order_by(RouteBandStop.sort_order)
    )
    stop_times_by_trip: dict[str, list[StopTime]] = {}
    for st in st_result.scalars().all():
        stop_times_by_trip.setdefault(st.trip_id, []).append(st)

    new_trip_ids: list[str] = []
    short_name_counter = 0  # running counter across all created trips

    def _apply_offset(stop_times: list[StopTime], offset_secs: int) -> list[dict]:
        """Return list of adjusted field dicts (arrival_time, departure_time)."""
        rows = []
        for st in stop_times:
            arr = _time_to_seconds(st.arrival_time)
            dep = _time_to_seconds(st.departure_time)
            new_arr = (_seconds_to_gtfs_time(arr + offset_secs) if arr is not None else None)
            new_dep = (_seconds_to_gtfs_time(dep + offset_secs) if dep is not None else None)
            rows.append({
                "route_band_stop_id":   st.route_band_stop_id,
                "arrival_time":         new_arr,
                "departure_time":       new_dep,
                "stop_headsign_id":     st.stop_headsign_id,
                "pickup_type":          st.pickup_type,
                "drop_off_type":        st.drop_off_type,
                "continuous_pickup":    st.continuous_pickup,
                "continuous_drop_off":  st.continuous_drop_off,
                "shape_dist_traveled":  st.shape_dist_traveled,
                "timepoint":            st.timepoint,
            })
        return rows

    def _create_trip_copy(source: Trip, offset_secs: int, service_id_override: str | None,
                          short_name_override: str | None) -> Trip:
        direction_str = str(source.direction_id) if source.direction_id is not None else "0"
        new_trip = Trip(
            version_id=version_id,
            trip_id=f"{route_id}-{direction_str}-{secrets.token_hex(3)}",
            route_id=route_id,
            service_id=service_id_override if service_id_override is not None else source.service_id,
            direction_id=source.direction_id,
            trip_short_name=short_name_override,
            trip_headsign_id=source.trip_headsign_id,
            block_id=source.block_id,
            shape_id=source.shape_id,
            wheelchair_accessible=source.wheelchair_accessible,
            bikes_allowed=source.bikes_allowed,
            cars_allowed=source.cars_allowed,
        )
        return new_trip

    for source_trip in source_trips:
        src_stop_times = stop_times_by_trip.get(source_trip.trip_id, [])

        # Determine offsets to apply
        if req.mode == "shift":
            s = req.shift  # type: ignore[union-attr]
            offset = s.offset_minutes * 60
            if s.direction == "backward":
                offset = -offset
            # Validate no negative times
            for st in src_stop_times:
                for attr in ("arrival_time", "departure_time"):
                    val = _time_to_seconds(getattr(st, attr))
                    if val is not None and val + offset < 0:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Shift would produce a negative time for trip '{source_trip.trip_id}'.",
                        )
            offsets = [offset]
        else:
            # Headway mode: compute base time (first departure of the source trip)
            h = req.headway  # type: ignore[union-attr]
            start_secs = _time_to_seconds(h.start_time)
            end_secs   = _time_to_seconds(h.end_time)
            headway_secs = h.headway_minutes * 60

            if start_secs is None or end_secs is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    detail="Invalid start_time or end_time")
            if end_secs <= start_secs:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    detail="end_time must be after start_time")

            # Find base = first departure time
            base_secs: int | None = None
            for st in src_stop_times:
                cand = _time_to_seconds(st.departure_time or st.arrival_time)
                if cand is not None:
                    base_secs = cand
                    break

            if base_secs is None:
                continue  # no times on this trip → skip

            offsets = []
            slot = start_secs
            while slot <= end_secs:
                offsets.append(slot - base_secs)
                slot += headway_secs

        for offset_secs in offsets:
            short_name: str | None = None
            if req.short_name_start is not None:
                pad_width = len(req.short_name_start.lstrip('-'))
                numeric = int(req.short_name_start) + short_name_counter * req.short_name_step
                short_name = str(numeric).zfill(pad_width)
            short_name_counter += 1

            new_trip = _create_trip_copy(source_trip, offset_secs, req.service_id, short_name)
            session.add(new_trip)
            await session.flush()

            # Copy stop times
            for row in _apply_offset(src_stop_times, offset_secs):
                new_st = StopTime(
                    version_id=version_id,
                    trip_id=new_trip.trip_id,
                    **row,
                )
                session.add(new_st)

            new_trip_ids.append(new_trip.trip_id)

    await session.flush()
    for tid in new_trip_ids:
        await _refresh_trip_hashes(version_id, tid, session)
    await session.commit()


# ===========================================================================
# StopTimes
# ===========================================================================

async def _get_route_band_stop_or_404(
    route_band_stop_id: uuid.UUID,
    session: AsyncSession,
) -> RouteBandStop:
    result = await session.execute(
        select(RouteBandStop).where(RouteBandStop.id == route_band_stop_id)
    )
    rbs = result.scalar_one_or_none()
    if rbs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Route band stop not found")
    return rbs


# ---- Schemas ---------------------------------------------------------------

class StopTimeOut(BaseModel):
    version_id:           uuid.UUID
    trip_id:              str
    route_band_stop_id:   uuid.UUID
    arrival_time:         str | None
    departure_time:       str | None
    stop_headsign_id:     str | None
    pickup_type:          int | None
    drop_off_type:        int | None
    continuous_pickup:    int | None
    continuous_drop_off:  int | None
    shape_dist_traveled:  float | None
    timepoint:            int | None

    model_config = {"from_attributes": True}


class StopTimeUpsert(BaseModel):
    arrival_time:        str | None = None
    departure_time:      str | None = None
    stop_headsign_id:    str | None = None
    pickup_type:         int | None = None
    drop_off_type:       int | None = None
    continuous_pickup:   int | None = None
    continuous_drop_off: int | None = None
    shape_dist_traveled: float | None = None
    timepoint:           int | None = None

    @field_validator("arrival_time", "departure_time", mode="before")
    @classmethod
    def validate_time_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import re
        raw = v.strip()
        if not re.fullmatch(r"\d+:\d{2}(:\d{2})?", raw):
            raise ValueError("Time must be in H:MM or H:MM:SS format")
        parts = raw.split(":")
        hh = parts[0].zfill(2)
        mm = parts[1]
        ss = parts[2] if len(parts) == 3 else "00"
        return f"{hh}:{mm}:{ss}"


# ---- Endpoints -------------------------------------------------------------

@router.get(
    "/{route_id}/trips/{trip_id}/stop-times",
    response_model=list[StopTimeOut],
    summary="List all stop times for a trip",
    dependencies=[require(Permission.SCHEDULE_READ)],
)
async def list_stop_times(
    version_id: uuid.UUID,
    route_id:   str,
    trip_id:    str,
    _:          User          = Depends(get_current_user),
    session:    AsyncSession  = Depends(get_session),
) -> list[StopTime]:
    await _get_version_or_404(version_id, session)
    await _get_trip_or_404(version_id, route_id, trip_id, session)

    result = await session.execute(
        select(StopTime)
        .where(StopTime.version_id == version_id, StopTime.trip_id == trip_id)
        .join(StopTime.route_band_stop)
        .order_by(RouteBandStop.sort_order)
    )
    return list(result.scalars().all())


@router.put(
    "/{route_id}/trips/{trip_id}/stop-times/{route_band_stop_id}",
    response_model=StopTimeOut,
    summary="Upsert a stop time for a specific route band position",
    dependencies=[require(Permission.SCHEDULE_WRITE)],
)
async def upsert_stop_time(
    version_id:         uuid.UUID,
    route_id:           str,
    trip_id:            str,
    route_band_stop_id: uuid.UUID,
    body:               StopTimeUpsert,
    _:                  User          = Depends(get_current_user),
    session:            AsyncSession  = Depends(get_session),
) -> StopTime:
    await _get_version_or_404(version_id, session)
    await _get_trip_or_404(version_id, route_id, trip_id, session)
    rbs = await _get_route_band_stop_or_404(route_band_stop_id, session)

    # Ensure the route_band_stop belongs to this version/route
    if rbs.version_id != version_id or rbs.route_id != route_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="route_band_stop does not belong to this version/route")

    result = await session.execute(
        select(StopTime).where(
            StopTime.version_id         == version_id,
            StopTime.trip_id            == trip_id,
            StopTime.route_band_stop_id == route_band_stop_id,
        )
    )
    st = result.scalar_one_or_none()

    if st is None:
        st = StopTime(
            version_id=version_id,
            trip_id=trip_id,
            route_band_stop_id=route_band_stop_id,
        )
        session.add(st)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(st, field, value)

    await session.flush()
    await _refresh_trip_hashes(version_id, trip_id, session)
    await session.commit()
    await session.refresh(st)
    return st


@router.delete(
    "/{route_id}/trips/{trip_id}/stop-times/{route_band_stop_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a single stop time entry",
    dependencies=[require(Permission.SCHEDULE_DELETE)],
)
async def delete_stop_time(
    version_id:         uuid.UUID,
    route_id:           str,
    trip_id:            str,
    route_band_stop_id: uuid.UUID,
    _:                  User          = Depends(get_current_user),
    session:            AsyncSession  = Depends(get_session),
) -> None:
    await _get_version_or_404(version_id, session)
    await _get_trip_or_404(version_id, route_id, trip_id, session)

    result = await session.execute(
        select(StopTime).where(
            StopTime.version_id         == version_id,
            StopTime.trip_id            == trip_id,
            StopTime.route_band_stop_id == route_band_stop_id,
        )
    )
    st = result.scalar_one_or_none()
    if st is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Stop time not found")
    await session.delete(st)
    await session.flush()
    await _refresh_trip_hashes(version_id, trip_id, session)
    await session.commit()

