"""Version copy service.

Copies selected data from a source version into a newly created target
version (or an existing one) and yields SSE-compatible status dicts.

Emitted events
--------------
{"status": "running"}
{"status": "done",  "version": {"id": "...", "name": "...", "created_at": "..."}}
{"status": "error", "message": "<reason>"}

When *target_version_id* is None a new version is created from *new_name*.
When *target_version_id* is provided the data is merged into that existing
version: entities whose primary key already exists in the target are skipped,
route bands are replaced/updated and the corresponding StopTime references
inside the target version are remapped accordingly.
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
    Headsign,
    Route,
    RouteBandStop,
    Shape,
    ShapeIntermediatePoint,
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
    new_name: str | None,
    target_version_id: uuid.UUID | None,
    include_agencies: bool,
    include_day_types: bool,
    include_stops: bool,
    include_shapes: bool,
    include_routes: bool,
    include_route_bands: bool,
    include_schedule: bool,
    include_headsigns: bool,
    session: AsyncSession,
) -> AsyncGenerator[dict[str, Any], None]:
    """Copy version data and stream status events.

    Pass *new_name* (and leave *target_version_id* as None) to create a fresh
    version.  Pass *target_version_id* (and leave *new_name* as None) to merge
    into an existing version.
    """
    yield {"status": "running"}

    rbs_id_map: dict[uuid.UUID, uuid.UUID] = {}

    if target_version_id is None:
        # ------------------------------------------------------------------ #
        # Create a brand-new target version                                   #
        # ------------------------------------------------------------------ #
        existing = await session.execute(select(Version).where(Version.name == new_name))
        if existing.scalar_one_or_none() is not None:
            yield {"status": "error", "message": "name_conflict"}
            return

        target_version = Version(name=new_name)
        session.add(target_version)
        await session.flush()
        new_vid: uuid.UUID = target_version.id

        try:
            if include_agencies:
                await _copy_agencies(session, source_version_id, new_vid)
            if include_day_types:
                await _copy_day_types(session, source_version_id, new_vid)
            if include_stops or include_shapes or include_schedule:
                await _copy_stops(session, source_version_id, new_vid)
            if include_shapes or include_schedule:
                await _copy_shapes(session, source_version_id, new_vid)
            if include_routes:
                await _copy_routes(session, source_version_id, new_vid)
            if include_route_bands:
                rbs_id_map = await _copy_route_bands(session, source_version_id, new_vid)
            headsign_id_map: dict[uuid.UUID, uuid.UUID] = {}
            if include_headsigns or include_schedule:
                headsign_id_map = await _copy_headsigns(session, source_version_id, new_vid)
            if include_schedule:
                await _copy_schedule(session, source_version_id, new_vid, rbs_id_map, headsign_id_map)

            await session.commit()
            await session.refresh(target_version)
            yield {
                "status": "done",
                "version": {
                    "id": str(target_version.id),
                    "name": target_version.name,
                    "created_at": target_version.created_at.isoformat(),
                    "sort_order": target_version.sort_order,
                },
            }

        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            yield {"status": "error", "message": str(exc)}

    else:
        # ------------------------------------------------------------------ #
        # Merge into an existing target version                               #
        # ------------------------------------------------------------------ #
        target_version = await session.get(Version, target_version_id)
        if target_version is None:
            yield {"status": "error", "message": "target_not_found"}
            return

        new_vid = target_version_id

        try:
            if include_agencies:
                await _merge_agencies(session, source_version_id, new_vid)
            if include_day_types:
                await _merge_day_types(session, source_version_id, new_vid)
            if include_stops or include_shapes or include_schedule:
                await _merge_stops(session, source_version_id, new_vid)
            if include_shapes or include_schedule:
                await _merge_shapes(session, source_version_id, new_vid)
            if include_routes:
                await _merge_routes(session, source_version_id, new_vid)
            if include_route_bands:
                rbs_id_map = await _merge_route_bands(session, source_version_id, new_vid)
            elif include_schedule:
                # No band update requested but we still need a src→dst id mapping
                # so that stop_times for newly copied trips can reference the
                # correct band stop entries in the target.
                rbs_id_map = await _get_src_to_dst_rbs_map(session, source_version_id, new_vid)
            headsign_id_map: dict[uuid.UUID, uuid.UUID] = {}
            if include_headsigns or include_schedule:
                headsign_id_map = await _merge_headsigns(session, source_version_id, new_vid)
            if include_schedule:
                await _merge_schedule(session, source_version_id, new_vid, rbs_id_map, headsign_id_map)

            await session.commit()
            await session.refresh(target_version)
            yield {
                "status": "done",
                "version": {
                    "id": str(target_version.id),
                    "name": target_version.name,
                    "created_at": target_version.created_at.isoformat(),
                    "sort_order": target_version.sort_order,
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
            global_id=r.global_id,
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
            global_id=s.global_id,
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
            global_id=r.global_id,
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


async def _copy_shapes(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> None:
    """Copy all shapes and their intermediate points from source to destination."""
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
            description=s.description,
            route_type=s.route_type,
            is_autoroute_active=s.is_autoroute_active,
        ))
    await session.flush()

    points = (
        await session.execute(
            select(ShapeIntermediatePoint).where(
                ShapeIntermediatePoint.version_id == src_vid
            )
        )
    ).scalars().all()
    for p in points:
        session.add(ShapeIntermediatePoint(
            version_id=dst_vid,
            shape_id=p.shape_id,
            sort_order=p.sort_order,
            lat=p.lat,
            lon=p.lon,
            stop_id=p.stop_id,
        ))


async def _merge_shapes(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> None:
    """Copy shapes (and their intermediate points) that do not yet exist in destination."""
    existing_shapes = set(
        (await session.execute(
            select(Shape.shape_id).where(Shape.version_id == dst_vid)
        )).scalars().all()
    )
    shapes = (
        await session.execute(select(Shape).where(Shape.version_id == src_vid))
    ).scalars().all()
    new_shape_ids: set[str] = set()
    for s in shapes:
        if s.shape_id not in existing_shapes:
            new_shape_ids.add(s.shape_id)
            session.add(Shape(
                version_id=dst_vid,
                shape_id=s.shape_id,
                shape_name=s.shape_name,
                shape_polyline=s.shape_polyline,
                routed_polyline=s.routed_polyline,
                description=s.description,
                route_type=s.route_type,
                is_autoroute_active=s.is_autoroute_active,
            ))
    await session.flush()

    if new_shape_ids:
        points = (
            await session.execute(
                select(ShapeIntermediatePoint).where(
                    ShapeIntermediatePoint.version_id == src_vid,
                    ShapeIntermediatePoint.shape_id.in_(new_shape_ids),
                )
            )
        ).scalars().all()
        for p in points:
            session.add(ShapeIntermediatePoint(
                version_id=dst_vid,
                shape_id=p.shape_id,
                sort_order=p.sort_order,
                lat=p.lat,
                lon=p.lon,
                stop_id=p.stop_id,
            ))


async def _copy_headsigns(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> dict[uuid.UUID, uuid.UUID]:
    """Copy all headsigns and return old_id → new_id mapping."""
    headsign_id_map: dict[uuid.UUID, uuid.UUID] = {}
    rows = (
        await session.execute(select(Headsign).where(Headsign.version_id == src_vid))
    ).scalars().all()
    for h in rows:
        new_id = uuid.uuid4()
        headsign_id_map[h.id] = new_id
        session.add(Headsign(
            id=new_id,
            version_id=dst_vid,
            name=h.name,
            number=h.number,
            destination=h.destination,
        ))
    await session.flush()
    return headsign_id_map


async def _merge_headsigns(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> dict[uuid.UUID, uuid.UUID]:
    """Merge headsigns by name; return src_id → dst_id mapping for all src headsigns.

    Headsigns that already exist in the destination (matched by name) are reused
    and their dst ID is placed in the map.  New headsigns are created.
    """
    dst_by_name: dict[str, uuid.UUID] = {
        h.name: h.id
        for h in (
            await session.execute(select(Headsign).where(Headsign.version_id == dst_vid))
        ).scalars().all()
    }
    headsign_id_map: dict[uuid.UUID, uuid.UUID] = {}
    src_rows = (
        await session.execute(select(Headsign).where(Headsign.version_id == src_vid))
    ).scalars().all()
    for h in src_rows:
        if h.name in dst_by_name:
            headsign_id_map[h.id] = dst_by_name[h.name]
        else:
            new_id = uuid.uuid4()
            headsign_id_map[h.id] = new_id
            dst_by_name[h.name] = new_id
            session.add(Headsign(
                id=new_id,
                version_id=dst_vid,
                name=h.name,
                number=h.number,
                destination=h.destination,
            ))
    await session.flush()
    return headsign_id_map


async def _copy_schedule(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
    rbs_id_map: dict[uuid.UUID, uuid.UUID],
    headsign_id_map: dict[uuid.UUID, uuid.UUID] | None = None,
) -> None:
    """Copy trips and stop_times."""
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
            trip_headsign_id=headsign_id_map.get(t.trip_headsign_id) if (headsign_id_map and t.trip_headsign_id) else None,
            block_id=t.block_id,
            shape_id=t.shape_id,
            wheelchair_accessible=t.wheelchair_accessible,
            bikes_allowed=t.bikes_allowed,
            cars_allowed=t.cars_allowed,
            global_id=t.global_id,
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
            stop_headsign_id=headsign_id_map.get(st.stop_headsign_id) if (headsign_id_map and st.stop_headsign_id) else None,
            pickup_type=st.pickup_type,
            drop_off_type=st.drop_off_type,
            continuous_pickup=st.continuous_pickup,
            continuous_drop_off=st.continuous_drop_off,
            shape_dist_traveled=st.shape_dist_traveled,
            timepoint=st.timepoint,
        ))


# ---------------------------------------------------------------------------
# Merge helpers — copy only entities that do not yet exist in target
# ---------------------------------------------------------------------------

async def _merge_agencies(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> None:
    existing = set(
        (await session.execute(
            select(Agency.agency_id).where(Agency.version_id == dst_vid)
        )).scalars().all()
    )
    rows = (
        await session.execute(select(Agency).where(Agency.version_id == src_vid))
    ).scalars().all()
    for r in rows:
        if r.agency_id not in existing:
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


async def _merge_day_types(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> dict[uuid.UUID, uuid.UUID]:
    """Merge aux_calendars, calendar_dates, calendars, and assignments.

    Only entities whose natural key (name / service_id) is not yet present in
    the target version are copied.  Returns a mapping of
    old src aux_calendar.id → new dst aux_calendar.id for the newly created
    entries (needed to wire up CalendarAuxCalendar assignments).
    """
    aux_id_map: dict[uuid.UUID, uuid.UUID] = {}

    existing_aux_names = set(
        (await session.execute(
            select(AuxCalendar.name).where(AuxCalendar.version_id == dst_vid)
        )).scalars().all()
    )
    existing_service_ids = set(
        (await session.execute(
            select(Calendar.service_id).where(Calendar.version_id == dst_vid)
        )).scalars().all()
    )

    # Aux calendars
    aux_cals = (
        await session.execute(
            select(AuxCalendar).where(AuxCalendar.version_id == src_vid)
        )
    ).scalars().all()
    for a in aux_cals:
        if a.name not in existing_aux_names:
            new_id = uuid.uuid4()
            aux_id_map[a.id] = new_id
            session.add(AuxCalendar(id=new_id, version_id=dst_vid, name=a.name))

    await session.flush()

    # Aux calendar dates for newly created aux_cals
    for old_id, new_id in aux_id_map.items():
        dates = (
            await session.execute(
                select(AuxCalendarDate).where(AuxCalendarDate.aux_calendar_id == old_id)
            )
        ).scalars().all()
        for d in dates:
            session.add(AuxCalendarDate(aux_calendar_id=new_id, date=d.date))

    # Calendars — skip service_ids already in dst
    cals = (
        await session.execute(
            select(Calendar).where(Calendar.version_id == src_vid)
        )
    ).scalars().all()
    new_service_ids: set[str] = set()
    for c in cals:
        if c.service_id not in existing_service_ids:
            new_service_ids.add(c.service_id)
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

    # Assignments — only for newly created service_ids with newly created aux_cals
    assignments = (
        await session.execute(
            select(CalendarAuxCalendar).where(CalendarAuxCalendar.version_id == src_vid)
        )
    ).scalars().all()
    for a in assignments:
        if a.service_id not in new_service_ids:
            continue
        new_aux_id = aux_id_map.get(a.aux_calendar_id)
        if new_aux_id is None:
            continue
        session.add(CalendarAuxCalendar(
            version_id=dst_vid,
            service_id=a.service_id,
            aux_calendar_id=new_aux_id,
            junction_type=a.junction_type,
        ))

    return aux_id_map


async def _merge_stops(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> None:
    existing = set(
        (await session.execute(
            select(Stop.stop_id).where(Stop.version_id == dst_vid)
        )).scalars().all()
    )
    rows = (
        await session.execute(select(Stop).where(Stop.version_id == src_vid))
    ).scalars().all()
    for s in rows:
        if s.stop_id not in existing:
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


async def _merge_routes(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> None:
    existing = set(
        (await session.execute(
            select(Route.route_id).where(Route.version_id == dst_vid)
        )).scalars().all()
    )
    rows = (
        await session.execute(select(Route).where(Route.version_id == src_vid))
    ).scalars().all()
    for r in rows:
        if r.route_id not in existing:
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


async def _merge_route_bands(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> dict[uuid.UUID, uuid.UUID]:
    """Merge route band stops from source into target.

    For every (route_id, direction) band present in the source:
    - Pre-generate new UUIDs for each source band stop.
    - If the band already exists in the target: load any existing StopTimes
      that reference old band stop IDs, save their data with remapped IDs
      (matched by stop_id within the same band), delete the old StopTimes,
      then delete the old band stops, THEN insert the new band stops, and
      finally re-insert the remapped StopTimes.
      This order is required to avoid the unique constraint violation on
      (version_id, route_id, direction, sort_order) that would occur if new
      rows were inserted before old ones were removed.
    - If the band does not yet exist in the target: simply insert new band stops.

    StopTimes referencing a stop that no longer appears in the new band are
    dropped (the stop was removed from the band in the source version).

    Returns a mapping  source RouteBandStop.id → new target RouteBandStop.id
    so that _merge_schedule can wire up stop_times for newly copied trips.
    """
    # ------------------------------------------------------------------ #
    # 1.  Load source and existing destination band stops                 #
    # ------------------------------------------------------------------ #
    src_rows = (
        await session.execute(
            select(RouteBandStop).where(RouteBandStop.version_id == src_vid)
        )
    ).scalars().all()

    src_by_band: dict[tuple, list[RouteBandStop]] = {}
    for r in src_rows:
        src_by_band.setdefault((r.route_id, r.direction), []).append(r)

    dst_rows = (
        await session.execute(
            select(RouteBandStop).where(RouteBandStop.version_id == dst_vid)
        )
    ).scalars().all()

    dst_by_band: dict[tuple, list[RouteBandStop]] = {}
    for r in dst_rows:
        dst_by_band.setdefault((r.route_id, r.direction), []).append(r)

    # ------------------------------------------------------------------ #
    # 2.  Pre-generate new UUIDs and build id-maps                        #
    # ------------------------------------------------------------------ #
    # src_rbs_id_map:  src_rbs.id  →  new_dst_rbs_id  (returned to caller)
    # old_to_new:      old_dst_rbs.id  →  new_dst_rbs_id  (for remapping existing stop_times)
    # new_rbs_objects: RouteBandStop instances to add after deletions
    src_rbs_id_map: dict[uuid.UUID, uuid.UUID] = {}
    old_to_new:     dict[uuid.UUID, uuid.UUID] = {}
    new_rbs_objects: list[RouteBandStop] = []

    for band_key, src_stops in src_by_band.items():
        # Map stop_id → newly generated UUID within this band
        new_by_stop_id: dict[str, uuid.UUID] = {}
        for src_stop in sorted(src_stops, key=lambda s: s.sort_order):
            new_id = uuid.uuid4()
            src_rbs_id_map[src_stop.id] = new_id
            new_by_stop_id[src_stop.stop_id] = new_id
            new_rbs_objects.append(RouteBandStop(
                id=new_id,
                version_id=dst_vid,
                route_id=src_stop.route_id,
                direction=src_stop.direction,
                stop_id=src_stop.stop_id,
                sort_order=src_stop.sort_order,
            ))

        # For each existing dst band stop: find which new UUID it maps to
        # (match by stop_id — this is how we "follow" a stop to its new position)
        for old_stop in dst_by_band.get(band_key, []):
            new_id = new_by_stop_id.get(old_stop.stop_id)
            if new_id is not None:
                old_to_new[old_stop.id] = new_id

    # ------------------------------------------------------------------ #
    # 3.  Collect all old dst band stop IDs for bands that exist in src   #
    # ------------------------------------------------------------------ #
    all_old_rbs_ids: list[uuid.UUID] = [
        old_stop.id
        for band_key in src_by_band
        for old_stop in dst_by_band.get(band_key, [])
    ]

    # ------------------------------------------------------------------ #
    # 4.  Load existing stop_times and save remapped data for later        #
    # ------------------------------------------------------------------ #
    remapped_st_data: list[dict] = []   # raw dicts; inserted after new band stops exist

    if all_old_rbs_ids:
        old_sts = (
            await session.execute(
                select(StopTime).where(
                    StopTime.version_id == dst_vid,
                    StopTime.route_band_stop_id.in_(all_old_rbs_ids),
                )
            )
        ).scalars().all()

        for st in old_sts:
            new_rbs_id = old_to_new.get(st.route_band_stop_id)
            if new_rbs_id is not None:
                # Capture data now; the new band stop row doesn't exist yet so
                # we cannot use session.add(StopTime(...)) at this point.
                remapped_st_data.append({
                    "version_id":          st.version_id,
                    "trip_id":             st.trip_id,
                    "route_band_stop_id":  new_rbs_id,
                    "arrival_time":        st.arrival_time,
                    "departure_time":      st.departure_time,
                    "stop_headsign_id":    st.stop_headsign_id,
                    "pickup_type":         st.pickup_type,
                    "drop_off_type":       st.drop_off_type,
                    "continuous_pickup":   st.continuous_pickup,
                    "continuous_drop_off": st.continuous_drop_off,
                    "shape_dist_traveled": st.shape_dist_traveled,
                    "timepoint":           st.timepoint,
                })
            # Delete old stop_time explicitly (do not rely on DB-level cascade
            # which would leave stale objects in the session identity map).
            await session.delete(st)

        await session.flush()   # ← stop_times gone from DB

    # ------------------------------------------------------------------ #
    # 5.  Delete old band stops (unique constraint is now satisfied)       #
    # ------------------------------------------------------------------ #
    for band_key in src_by_band:
        for old_stop in dst_by_band.get(band_key, []):
            obj = await session.get(RouteBandStop, old_stop.id)
            if obj is not None:
                await session.delete(obj)

    await session.flush()   # ← old band stops gone; (version, route, dir, sort_order) slots freed

    # ------------------------------------------------------------------ #
    # 6.  Insert new band stops                                            #
    # ------------------------------------------------------------------ #
    for rbs in new_rbs_objects:
        session.add(rbs)

    await session.flush()   # ← new band stops visible in DB

    # ------------------------------------------------------------------ #
    # 7.  Re-insert remapped stop_times with new band stop references      #
    # ------------------------------------------------------------------ #
    for data in remapped_st_data:
        session.add(StopTime(**data))

    await session.flush()

    return src_rbs_id_map


async def _get_src_to_dst_rbs_map(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
) -> dict[uuid.UUID, uuid.UUID]:
    """Build a mapping source RouteBandStop.id → target RouteBandStop.id
    by matching on (route_id, direction, stop_id).

    Used when include_schedule=True but include_route_bands=False during a
    merge, so that stop_times for newly copied trips can reference the correct
    band stop entries that already exist in the target version.
    """
    src_rows = (
        await session.execute(
            select(RouteBandStop).where(RouteBandStop.version_id == src_vid)
        )
    ).scalars().all()
    dst_rows = (
        await session.execute(
            select(RouteBandStop).where(RouteBandStop.version_id == dst_vid)
        )
    ).scalars().all()

    dst_idx = {(r.route_id, r.direction, r.stop_id): r.id for r in dst_rows}

    mapping: dict[uuid.UUID, uuid.UUID] = {}
    for src in src_rows:
        dst_id = dst_idx.get((src.route_id, src.direction, src.stop_id))
        if dst_id is not None:
            mapping[src.id] = dst_id
    return mapping


async def _merge_schedule(
    session: AsyncSession,
    src_vid: uuid.UUID,
    dst_vid: uuid.UUID,
    rbs_id_map: dict[uuid.UUID, uuid.UUID],
    headsign_id_map: dict[uuid.UUID, uuid.UUID] | None = None,
) -> None:
    """Merge trips and stop_times that do not yet exist in target."""
    # Trips
    existing_trips = set(
        (await session.execute(
            select(Trip.trip_id).where(Trip.version_id == dst_vid)
        )).scalars().all()
    )
    trips = (
        await session.execute(select(Trip).where(Trip.version_id == src_vid))
    ).scalars().all()
    new_trip_ids: set[str] = set()
    for t in trips:
        if t.trip_id not in existing_trips:
            new_trip_ids.add(t.trip_id)
            session.add(Trip(
                version_id=dst_vid,
                trip_id=t.trip_id,
                route_id=t.route_id,
                service_id=t.service_id,
                direction_id=t.direction_id,
                trip_short_name=t.trip_short_name,
                trip_headsign_id=headsign_id_map.get(t.trip_headsign_id) if (headsign_id_map and t.trip_headsign_id) else None,
                block_id=t.block_id,
                shape_id=t.shape_id,
                wheelchair_accessible=t.wheelchair_accessible,
                bikes_allowed=t.bikes_allowed,
                cars_allowed=t.cars_allowed,
                geo_pattern_hash=t.geo_pattern_hash,
                schedule_pattern_hash=t.schedule_pattern_hash,
            ))

    await session.flush()

    if not new_trip_ids or not rbs_id_map:
        return

    # Stop times — only for newly copied trips, rbs_id must be remapped
    stop_times = (
        await session.execute(
            select(StopTime).where(
                StopTime.version_id == src_vid,
                StopTime.trip_id.in_(new_trip_ids),
            )
        )
    ).scalars().all()
    for st in stop_times:
        new_rbs_id = rbs_id_map.get(st.route_band_stop_id)
        if new_rbs_id is None:
            continue
        session.add(StopTime(
            version_id=dst_vid,
            trip_id=st.trip_id,
            route_band_stop_id=new_rbs_id,
            arrival_time=st.arrival_time,
            departure_time=st.departure_time,
            stop_headsign_id=headsign_id_map.get(st.stop_headsign_id) if (headsign_id_map and st.stop_headsign_id) else None,
            pickup_type=st.pickup_type,
            drop_off_type=st.drop_off_type,
            continuous_pickup=st.continuous_pickup,
            continuous_drop_off=st.continuous_drop_off,
            shape_dist_traveled=st.shape_dist_traveled,
            timepoint=st.timepoint,
        ))
