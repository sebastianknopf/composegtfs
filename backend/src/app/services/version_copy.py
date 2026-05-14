"""Version copy service.

Copies selected data from a source version into a newly created target
version and yields SSE-compatible status dicts.

Emitted events
--------------
{"status": "running"}
{"status": "done",  "version": {"id": "...", "name": "...", "created_at": "..."}}
{"status": "error", "message": "<reason>"}
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Agency,
    AuxCalendar,
    AuxCalendarDate,
    Calendar,
    CalendarAuxCalendar,
    Route,
    RouteBandStop,
    Shape,
    Stop,
    StopTime,
    Trip,
    Version,
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_copy(
    *,
    source_version_id: uuid.UUID,
    new_name: str,
    include_agencies: bool,
    include_day_types: bool,
    include_stops: bool,
    include_routes: bool,
    include_route_bands: bool,
    include_schedule: bool,
    session: AsyncSession,
) -> AsyncGenerator[dict[str, Any], None]:
    """Copy version data and stream status events."""
    yield {"status": "running"}

    existing = await session.execute(select(Version).where(Version.name == new_name))
    if existing.scalar_one_or_none() is not None:
        yield {"status": "error", "message": "name_conflict"}
        return

    new_version = Version(name=new_name)
    session.add(new_version)
    await session.flush()
    new_vid: uuid.UUID = new_version.id

    aux_cal_id_map: dict[uuid.UUID, uuid.UUID] = {}
    rbs_id_map: dict[uuid.UUID, uuid.UUID] = {}

    try:
        if include_agencies:
            await _copy_agencies(session, source_version_id, new_vid)

        if include_day_types:
            aux_cal_id_map = await _copy_day_types(session, source_version_id, new_vid)

        if include_stops:
            await _copy_stops(session, source_version_id, new_vid)

        if include_routes:
            await _copy_routes(session, source_version_id, new_vid)

        if include_route_bands:
            rbs_id_map = await _copy_route_bands(session, source_version_id, new_vid)

        if include_schedule:
            await _copy_schedule(
                session, source_version_id, new_vid, rbs_id_map
            )

        await session.commit()
        await session.refresh(new_version)
        yield {
            "status": "done",
            "version": {
                "id": str(new_version.id),
                "name": new_version.name,
                "created_at": new_version.created_at.isoformat(),
            },
        }

    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        yield {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# Per-entity copy helpers
# ---------------------------------------------------------------------------

async def _copy_agencies(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> None:
    rows = (
        await session.execute(select(Agency).where(Agency.version_id == src_vid))
    ).scalars().all()
    for r in rows:
        session.add(Agency(
            version_id=dst_vid,
            agency_id=r.agency_id,
            agency_name=r.agency_name,
            agency_url=r.agency_url,
            agency_timezone=r.agency_timezone,
            agency_lang=r.agency_lang,
            agency_phone=r.agency_phone,
            agency_fare_url=r.agency_fare_url,
            agency_email=r.agency_email,
            cemv_support=r.cemv_support,
        ))


async def _copy_day_types(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> dict[uuid.UUID, uuid.UUID]:
    """Copy calendars, aux_calendars, aux_calendar_dates, and assignments.

    Returns a mapping of old aux_calendar.id → new aux_calendar.id.
    """
    aux_id_map: dict[uuid.UUID, uuid.UUID] = {}

    # Aux calendars
    aux_cals = (
        await session.execute(
            select(AuxCalendar).where(AuxCalendar.version_id == src_vid)
        )
    ).scalars().all()
    for a in aux_cals:
        new_id = uuid.uuid4()
        aux_id_map[a.id] = new_id
        session.add(AuxCalendar(id=new_id, version_id=dst_vid, name=a.name))

    await session.flush()

    # Aux calendar dates
    for old_id, new_id in aux_id_map.items():
        dates = (
            await session.execute(
                select(AuxCalendarDate).where(
                    AuxCalendarDate.aux_calendar_id == old_id
                )
            )
        ).scalars().all()
        for d in dates:
            session.add(AuxCalendarDate(aux_calendar_id=new_id, date=d.date))

    # Calendars (Tagesarten)
    cals = (
        await session.execute(
            select(Calendar).where(Calendar.version_id == src_vid)
        )
    ).scalars().all()
    for c in cals:
        session.add(Calendar(
            version_id=dst_vid,
            service_id=c.service_id,
            name=c.name,
            monday=c.monday,
            tuesday=c.tuesday,
            wednesday=c.wednesday,
            thursday=c.thursday,
            friday=c.friday,
            saturday=c.saturday,
            sunday=c.sunday,
            start_date=c.start_date,
            end_date=c.end_date,
        ))

    await session.flush()

    # Calendar ↔ AuxCalendar assignments
    assignments = (
        await session.execute(
            select(CalendarAuxCalendar).where(
                CalendarAuxCalendar.version_id == src_vid
            )
        )
    ).scalars().all()
    for a in assignments:
        new_aux_id = aux_id_map.get(a.aux_calendar_id)
        if new_aux_id is not None:
            session.add(CalendarAuxCalendar(
                version_id=dst_vid,
                service_id=a.service_id,
                aux_calendar_id=new_aux_id,
                junction_type=a.junction_type,
            ))

    return aux_id_map


async def _copy_stops(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> None:
    # parent_station FK is DEFERRED so we can insert all rows in one pass.
    rows = (
        await session.execute(select(Stop).where(Stop.version_id == src_vid))
    ).scalars().all()
    for s in rows:
        session.add(Stop(
            version_id=dst_vid,
            stop_id=s.stop_id,
            stop_code=s.stop_code,
            stop_name=s.stop_name,
            tts_stop_name=s.tts_stop_name,
            stop_desc=s.stop_desc,
            stop_lat=s.stop_lat,
            stop_lon=s.stop_lon,
            zone_id=s.zone_id,
            stop_url=s.stop_url,
            location_type=s.location_type,
            parent_station=s.parent_station,
            stop_timezone=s.stop_timezone,
            wheelchair_boarding=s.wheelchair_boarding,
            level_id=s.level_id,
            platform_code=s.platform_code,
            stop_access=s.stop_access,
        ))


async def _copy_routes(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> None:
    rows = (
        await session.execute(select(Route).where(Route.version_id == src_vid))
    ).scalars().all()
    for r in rows:
        session.add(Route(
            version_id=dst_vid,
            route_id=r.route_id,
            agency_id=r.agency_id,
            route_short_name=r.route_short_name,
            route_long_name=r.route_long_name,
            route_desc=r.route_desc,
            route_type=r.route_type,
            route_url=r.route_url,
            route_color=r.route_color,
            route_text_color=r.route_text_color,
            route_sort_order=r.route_sort_order,
            continuous_pickup=r.continuous_pickup,
            continuous_drop_off=r.continuous_drop_off,
            network_id=r.network_id,
            cemv_support=r.cemv_support,
        ))


async def _copy_route_bands(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> dict[uuid.UUID, uuid.UUID]:
    """Copy route band stops and return old-id → new-id mapping."""
    rbs_id_map: dict[uuid.UUID, uuid.UUID] = {}
    rows = (
        await session.execute(
            select(RouteBandStop).where(RouteBandStop.version_id == src_vid)
        )
    ).scalars().all()
    for r in rows:
        new_id = uuid.uuid4()
        rbs_id_map[r.id] = new_id
        session.add(RouteBandStop(
            id=new_id,
            version_id=dst_vid,
            route_id=r.route_id,
            direction=r.direction,
            stop_id=r.stop_id,
            sort_order=r.sort_order,
        ))
    return rbs_id_map


async def _copy_schedule(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
    rbs_id_map: dict[uuid.UUID, uuid.UUID],
) -> None:
    """Copy shapes, trips, and stop_times."""
    # Shapes
    shapes = (
        await session.execute(select(Shape).where(Shape.version_id == src_vid))
    ).scalars().all()
    for s in shapes:
        session.add(Shape(
            version_id=dst_vid,
            shape_id=s.shape_id,
            shape_name=s.shape_name,
            shape_polyline=s.shape_polyline,
            routed_polyline=s.routed_polyline,
        ))

    await session.flush()

    # Trips
    trips = (
        await session.execute(select(Trip).where(Trip.version_id == src_vid))
    ).scalars().all()
    for t in trips:
        session.add(Trip(
            version_id=dst_vid,
            trip_id=t.trip_id,
            route_id=t.route_id,
            service_id=t.service_id,
            direction_id=t.direction_id,
            trip_short_name=t.trip_short_name,
            trip_headsign_id=t.trip_headsign_id,
            block_id=t.block_id,
            shape_id=t.shape_id,
            wheelchair_accessible=t.wheelchair_accessible,
            bikes_allowed=t.bikes_allowed,
            cars_allowed=t.cars_allowed,
            geo_pattern_hash=t.geo_pattern_hash,
            schedule_pattern_hash=t.schedule_pattern_hash,
        ))

    await session.flush()

    # Stop times — route_band_stop_id must be remapped
    if not rbs_id_map:
        return

    stop_times = (
        await session.execute(
            select(StopTime).where(StopTime.version_id == src_vid)
        )
    ).scalars().all()
    for st in stop_times:
        new_rbs_id = rbs_id_map.get(st.route_band_stop_id)
        if new_rbs_id is None:
            continue  # band stop was not included in this copy
        session.add(StopTime(
            version_id=dst_vid,
            trip_id=st.trip_id,
            route_band_stop_id=new_rbs_id,
            arrival_time=st.arrival_time,
            departure_time=st.departure_time,
            stop_headsign_id=st.stop_headsign_id,
            pickup_type=st.pickup_type,
            drop_off_type=st.drop_off_type,
            continuous_pickup=st.continuous_pickup,
            continuous_drop_off=st.continuous_drop_off,
            shape_dist_traveled=st.shape_dist_traveled,
            timepoint=st.timepoint,
        ))
