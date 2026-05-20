"""GTFS Export Service — complete feed generation.

Builds a GTFS ZIP in memory and streams progress events
as an async generator to the calling router.

Included GTFS files (in export order)
--------------------------------------
  agency.txt          – all operators referenced by the selected routes
  routes.txt          – selected routes
  calendar.txt        – day types (calendars) used by exported trips
  calendar_dates.txt  – exceptions derived from auxiliary calendars, filtered to the export period
  shapes.txt          – route paths of exported trips; routed_polyline preferred
  trips.txt           – trips for the selected routes
  stops.txt           – all stops/platforms of the version
  stop_times.txt      – stop times derived from route band + StopTime table;
                        shape_dist_traveled is projected from the shape if a route path
                        exists, otherwise the stored value is used.

Event schema
------------
Each yielded dict contains at least:
  { "level":  "Info" | "LowPrio" | "MiddlePrio" | "HighPrio",
    "key":    "<i18n message key>",
    "params": { ... },
    "status": "running" | "done" | "error" }

The final "done" event additionally contains:
  "payload":  Base64-encoded ZIP
  "filename": suggested file name
"""

from __future__ import annotations

import base64
import csv
import io
import logging
import math
import uuid
import zipfile
import zlib
from collections import defaultdict
from datetime import date, timedelta
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Agency,
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

logger = logging.getLogger(__name__)

ExportEvent = dict[str, object]


def _log(level: str, key: str, params: dict | None = None, status: str = "running") -> ExportEvent:
    """Creates a structured log event with an i18n key, optional params, and a status."""
    return {"level": level, "key": key, "params": params or {}, "status": status}


def _build_export_id_map(
    items: list,
    get_internal_id,
    get_global_id,
    missing_key: str,
    missing_param_name: str,
    duplicate_key: str,
) -> tuple[dict[str, str], list[ExportEvent], list[ExportEvent]]:
    """Build an internal-ID → exported-ID map using global IDs.

    For each item:
    - If its global_id is empty/None, a MiddlePrio warning is emitted and the
      internal ID is used as fallback.
    - If its global_id duplicates one already seen, a HighPrio error is emitted
      and the duplicate is added to *error_events*.

    Returns ``(id_map, log_events, error_events)`` where *error_events* contains
    only the HighPrio duplicates.
    """
    id_map: dict[str, str] = {}
    log_events: list[ExportEvent] = []
    error_events: list[ExportEvent] = []
    seen: dict[str, str] = {}
    for item in items:
        internal_id = get_internal_id(item)
        exp: str | None = get_global_id(item) or None
        if exp is None:
            log_events.append(_log("MiddlePrio", missing_key, {missing_param_name: internal_id}))
            exp = internal_id
        elif exp in seen:
            evt = _log("HighPrio", duplicate_key, {"global_id": exp})
            log_events.append(evt)
            error_events.append(evt)
        seen[exp] = internal_id
        id_map[internal_id] = exp
    return id_map, log_events, error_events


# ---------------------------------------------------------------------------
# Geometry helper functions
# ---------------------------------------------------------------------------

def _decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """Decodes a Google Encoded Polyline string into a list of (lat, lon) tuples."""
    points: list[tuple[float, float]] = []
    idx, n = 0, len(encoded)
    lat = lon = 0
    while idx < n:
        lat_delta = lon_delta = 0
        for i in range(2):
            result = shift = 0
            while True:
                b = ord(encoded[idx]) - 63
                idx += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if i == 0:
                lat_delta = delta
            else:
                lon_delta = delta
        lat += lat_delta
        lon += lon_delta
        points.append((lat * 1e-5, lon * 1e-5))
    return points


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Returns the great-circle distance in metres between two WGS-84 points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2.0 * R * math.asin(math.sqrt(min(1.0, a)))


def _cumulative_distances_m(points: list[tuple[float, float]]) -> list[float]:
    """Returns cumulative haversine distances in metres starting from the first point."""
    cum = [0.0]
    for i in range(1, len(points)):
        cum.append(cum[-1] + _haversine_m(*points[i - 1], *points[i]))
    return cum


def _format_gtfs_time(t: str | None) -> str:
    """Ensure time is in hh:mm:ss format. Pads hh:mm to hh:mm:00."""
    if not t:
        return ""
    parts = t.split(":")
    if len(parts) == 2:
        return f"{parts[0]}:{parts[1]}:00"
    return t  # already hh:mm:ss or longer


def _shorten_shape_id(shape_id: str) -> str:
    """Returns an 8-character lowercase hex CRC32 of the shape_id."""
    return format(zlib.crc32(shape_id.encode()) & 0xFFFFFFFF, '08x')


def _project_stop_on_shape(
    slat: float,
    slon: float,
    shape_pts: list[tuple[float, float]],
    cum_dists: list[float],
    min_dist: float = 0.0,
) -> float:
    """Projects a stop position (lat/lon) onto the nearest shape segment at or after
    *min_dist* (metres) and returns the cumulative distance along the shape.

    *min_dist* keeps the result monotonically non-decreasing across a trip's stop
    sequence, which is required for circular routes where the same stop appears
    more than once.
    """
    if len(shape_pts) == 1:
        return max(0.0, min_dist)
    # Locate the last segment whose start is still <= min_dist so that we also
    # consider the segment that straddles min_dist.
    start_idx = 0
    for i in range(len(shape_pts) - 1):
        if cum_dists[i] <= min_dist:
            start_idx = i
        else:
            break
    best_dist_sq = math.inf
    best_shape_dist = min_dist  # fallback: maintain monotonicity
    for i in range(start_idx, len(shape_pts) - 1):
        ax, ay = shape_pts[i][1], shape_pts[i][0]        # (lon, lat)
        bx, by = shape_pts[i + 1][1], shape_pts[i + 1][0]
        px, py = slon, slat
        dx, dy = bx - ax, by - ay
        len_sq = dx * dx + dy * dy
        t = 0.0 if len_sq == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / len_sq))
        proj = cum_dists[i] + t * (cum_dists[i + 1] - cum_dists[i])
        proj = max(proj, min_dist)  # clamp straddling segment to min_dist
        cx, cy = ax + t * dx, ay + t * dy
        dist_sq = (px - cx) ** 2 + (py - cy) ** 2
        if dist_sq < best_dist_sq:
            best_dist_sq = dist_sq
            best_shape_dist = proj
    return best_shape_dist


# ---------------------------------------------------------------------------
# calendar_dates.txt — exception computation
# ---------------------------------------------------------------------------

def _base_dates_in_range(cal: Calendar, date_from: date, date_to: date) -> set[date]:
    """Enumerates all dates in the intersection of [cal.start_date, cal.end_date] and
    [date_from, date_to] that match the weekday pattern of the calendar.
    Returns: set[date]
    """
    # ISO weekday 1=Mon … 7=Sun; Python weekday() 0=Mon … 6=Sun
    DAY_FLAGS = [cal.monday, cal.tuesday, cal.wednesday,
                 cal.thursday, cal.friday, cal.saturday, cal.sunday]
    start = max(cal.start_date, date_from)
    end   = min(cal.end_date,   date_to)
    result: set[date] = set()
    if start > end:
        return result
    cur = start
    while cur <= end:
        if DAY_FLAGS[cur.weekday()]:
            result.add(cur)
        cur += timedelta(days=1)
    return result


def compute_calendar_exceptions(
    calendars: list[Calendar],
    cac_rows: list[CalendarAuxCalendar],
    aux_dates_by_aux_cal: dict[uuid.UUID, list[date]],
    date_from: date,
    date_to: date,
) -> list[tuple[str, date, int]]:
    """Computes the GTFS calendar_dates rows for all provided calendars.

    Logic (mirrors the frontend implementation in CalendarView.vue):
    ─────────────────────────────────────────────────────────────────
    1. base_dates = all dates in [max(start,date_from), min(end,date_to)]
                   that match the weekday pattern.
    2. junction_type 3 (only): all "only" auxiliary calendars are intersected;
       base_dates is restricted to this intersection.
    3. junction_type 1 (additional): dates are added to base_dates.
    4. junction_type 2 (not): dates are removed from base_dates.
    5. effective_dates = result after steps 2-4.

    GTFS exceptions = difference between effective_dates and original base_dates:
       effective - base  → exception_type 1 (added)
       base - effective  → exception_type 2 (removed)

    Returns: sorted list of (service_id, date, exception_type) tuples.
    This function can be disabled by not calling it and returning an empty list instead.
    """
    # Mapping: service_id → list of CalendarAuxCalendar rows
    cac_by_service: dict[str, list[CalendarAuxCalendar]] = defaultdict(list)
    for cac in cac_rows:
        cac_by_service[cac.service_id].append(cac)

    aux_dates_sets: dict[uuid.UUID, set[date]] = {
        aid: set(dates) for aid, dates in aux_dates_by_aux_cal.items()
    }

    rows: list[tuple[str, date, int]] = []

    for cal in calendars:
        base = _base_dates_in_range(cal, date_from, date_to)
        effective = set(base)  # working copy

        assignments = cac_by_service.get(cal.service_id, [])

        # Step 2: junction_type 3 (only) — intersection of all "only" auxiliary calendars
        nur_sets = [
            aux_dates_sets.get(cac.aux_calendar_id, set())
            for cac in assignments if cac.junction_type == 3
        ]
        if nur_sets:
            intersection: set[date] = nur_sets[0]
            for s in nur_sets[1:]:
                intersection = intersection & s
            # Restrict effective dates to those also in the intersection
            effective = effective & intersection
            # Dates in the intersection not in the base pattern are added
            effective |= (intersection - base)

        # Steps 3+4: junction_type 1 (additional) and 2 (not)
        for cac in assignments:
            dates = aux_dates_sets.get(cac.aux_calendar_id, set())
            if cac.junction_type == 1:
                effective |= dates
            elif cac.junction_type == 2:
                effective -= dates

        # GTFS exceptions: difference from the calendar.txt base set
        for dt in sorted(effective - base):
            rows.append((cal.service_id, dt, 1))  # added
        for dt in sorted(base - effective):
            rows.append((cal.service_id, dt, 2))  # removed

    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


# ---------------------------------------------------------------------------
# Reference pruning: export only stops that are actually used
# ---------------------------------------------------------------------------

def filter_referenced_stops(
    stops_by_id: dict[str, "Stop"],
    route_band_stop_ids: set[str],
) -> list["Stop"]:
    """Filters the stop list to those actually referenced by the route bands of
    the selected routes, plus their direct parent stations.

    This ensures stops.txt only contains entries that are actually used in the feed.

    This function can be disabled by using ``list(stops_by_id.values())`` instead.
    """
    referenced = set(route_band_stop_ids)
    # Also include parent stations of referenced platforms
    for stop in stops_by_id.values():
        if stop.stop_id in referenced and stop.parent_station:
            referenced.add(stop.parent_station)
    return sorted(
        (s for s in stops_by_id.values() if s.stop_id in referenced),
        key=lambda s: s.stop_id,
    )


# ---------------------------------------------------------------------------
# Main export generator
# ---------------------------------------------------------------------------

async def run_export(
    version_id: uuid.UUID,
    route_ids: list[str],
    date_from: date,
    date_to: date,
    session: AsyncSession,
    export_all_stops: bool = False,
    export_shapes: bool = True,
    prefer_global_ids: bool = False,
) -> AsyncGenerator[ExportEvent, None]:
    """Async generator: incrementally builds the GTFS feed and yields structured log events.

    The final event has status="done" and contains the completed ZIP as Base64 in "payload".
    """
    # ------------------------------------------------------------------
    # Check version
    # ------------------------------------------------------------------
    version = await session.get(Version, version_id)
    if version is None:
        yield _log("HighPrio", "version_not_found", {"version_id": str(version_id)}, "error")
        return

    route_ids_set = set(route_ids)

    # ------------------------------------------------------------------
    # Load all required data from the database
    # ------------------------------------------------------------------

    # Routes
    routes_q = await session.execute(
        select(Route)
        .where(Route.version_id == version_id, Route.route_id.in_(route_ids_set))
        .order_by(Route.route_id)
    )
    routes = routes_q.scalars().all()
    if not routes:
        yield _log("MiddlePrio", "no_routes_found")

    agency_ids_set = {r.agency_id for r in routes if r.agency_id}

    # Operators
    agencies_q = await session.execute(
        select(Agency)
        .where(Agency.version_id == version_id, Agency.agency_id.in_(agency_ids_set))
        .order_by(Agency.agency_id)
    )
    agencies = agencies_q.scalars().all()

    # Trips
    trips_q = await session.execute(
        select(Trip)
        .where(Trip.version_id == version_id, Trip.route_id.in_(route_ids_set))
        .order_by(Trip.route_id, Trip.trip_id)
    )
    trips = trips_q.scalars().all()
    trips_by_id: dict[str, Trip] = {t.trip_id: t for t in trips}
    trip_ids_set = set(trips_by_id)
    service_ids_set = {t.service_id for t in trips if t.service_id}
    shape_ids_set = {t.shape_id for t in trips if t.shape_id}

    # Calendars (day types)
    calendars: list[Calendar] = []
    if service_ids_set:
        cal_q = await session.execute(
            select(Calendar)
            .where(Calendar.version_id == version_id, Calendar.service_id.in_(service_ids_set))
            .order_by(Calendar.service_id)
        )
        calendars = cal_q.scalars().all()

    # Calendar exceptions: CalendarAuxCalendar + filtered AuxCalendarDate
    cac_rows: list[CalendarAuxCalendar] = []
    aux_dates_by_aux_cal: dict[uuid.UUID, list[date]] = defaultdict(list)
    if service_ids_set:
        cac_q = await session.execute(
            select(CalendarAuxCalendar)
            .where(
                CalendarAuxCalendar.version_id == version_id,
                CalendarAuxCalendar.service_id.in_(service_ids_set),
            )
        )
        cac_rows = cac_q.scalars().all()
        aux_cal_ids_set = {c.aux_calendar_id for c in cac_rows}
        if aux_cal_ids_set:
            adates_q = await session.execute(
                select(AuxCalendarDate)
                .where(
                    AuxCalendarDate.aux_calendar_id.in_(aux_cal_ids_set),
                    AuxCalendarDate.date >= date_from,
                    AuxCalendarDate.date <= date_to,
                )
            )
            for d in adates_q.scalars().all():
                aux_dates_by_aux_cal[d.aux_calendar_id].append(d.date)

    # Shapes
    shapes: list[Shape] = []
    if shape_ids_set:
        sh_q = await session.execute(
            select(Shape)
            .where(Shape.version_id == version_id, Shape.shape_id.in_(shape_ids_set))
            .order_by(Shape.shape_id)
        )
        shapes = sh_q.scalars().all()

    # Decode shapes (routed_polyline preferred) — once for later use
    shape_data: dict[str, tuple[list[tuple[float, float]], list[float]]] = {}
    for sh in shapes:
        poly = sh.routed_polyline or sh.shape_polyline
        if not poly:
            continue
        try:
            pts = _decode_polyline(poly)
            if pts:
                shape_data[sh.shape_id] = (pts, _cumulative_distances_m(pts))
        except Exception:  # noqa: BLE001
            logger.warning("Failed to decode shape %s.", sh.shape_id)

    # Stops (all for the version; also used as lookup for stop_times)
    stops_q = await session.execute(
        select(Stop).where(Stop.version_id == version_id).order_by(Stop.stop_id)
    )
    stops = stops_q.scalars().all()
    stops_by_id: dict[str, Stop] = {s.stop_id: s for s in stops}

    # Shape intermediate points — used as fallback when a shape has no usable polyline.
    # Grouped by shape_id, ordered by sort_order (the DB query guarantees this).
    sip_by_shape: dict[str, list[ShapeIntermediatePoint]] = defaultdict(list)
    if shape_ids_set:
        sip_q = await session.execute(
            select(ShapeIntermediatePoint)
            .where(
                ShapeIntermediatePoint.version_id == version_id,
                ShapeIntermediatePoint.shape_id.in_(shape_ids_set),
            )
            .order_by(ShapeIntermediatePoint.shape_id, ShapeIntermediatePoint.sort_order)
        )
        for pt in sip_q.scalars().all():
            sip_by_shape[pt.shape_id].append(pt)

    # Fill in shape_data for shapes that had no usable polyline, building the
    # coordinate sequence from their intermediate points instead.
    for sh in shapes:
        if sh.shape_id in shape_data:
            continue
        coords: list[tuple[float, float]] = []
        for ipt in sip_by_shape.get(sh.shape_id, []):
            if ipt.stop_id:
                stop = stops_by_id.get(ipt.stop_id)
                if stop and stop.stop_lat is not None and stop.stop_lon is not None:
                    coords.append((stop.stop_lat, stop.stop_lon))
            elif ipt.lat is not None and ipt.lon is not None:
                coords.append((ipt.lat, ipt.lon))
        if len(coords) >= 2:
            shape_data[sh.shape_id] = (coords, _cumulative_distances_m(coords))

    # All route band entries for the selected routes (for pruning + stop_times)
    all_rbs_q = await session.execute(
        select(RouteBandStop)
        .where(
            RouteBandStop.version_id == version_id,
            RouteBandStop.route_id.in_(route_ids_set),
        )
    )
    all_route_band_stops = all_rbs_q.scalars().all()
    referenced_stop_ids: set[str] = {rbs.stop_id for rbs in all_route_band_stops}

    # Headsigns — build id → destination text lookup
    hs_q = await session.execute(
        select(Headsign).where(Headsign.version_id == version_id)
    )
    headsign_map: dict[uuid.UUID, str] = {
        h.id: h.destination for h in hs_q.scalars().all()
    }

    # Stop times with route band entries (join via route_band_stop_id)
    st_rows: list = []
    if trip_ids_set:
        st_q = await session.execute(
            select(StopTime, RouteBandStop)
            .join(RouteBandStop, StopTime.route_band_stop_id == RouteBandStop.id)
            .where(
                StopTime.version_id == version_id,
                StopTime.trip_id.in_(trip_ids_set),
            )
            .order_by(StopTime.trip_id, RouteBandStop.sort_order)
        )
        st_rows = st_q.all()

    # ── Restrict calendars to the export period ─────────────────────────────
    # Day types with no active days in the export period are discarded;
    # associated trips and stop times are filtered out as well.
    _cac_by_svc: dict[str, list] = defaultdict(list)
    for _cac in cac_rows:
        _cac_by_svc[_cac.service_id].append(_cac)
    _aux_sets: dict[uuid.UUID, set[date]] = {
        aid: set(ds) for aid, ds in aux_dates_by_aux_cal.items()
    }
    _svc_effective: dict[str, set[date]] = {}
    for _cal in calendars:
        _base = _base_dates_in_range(_cal, date_from, date_to)
        _eff: set[date] = set(_base)
        _assignments = _cac_by_svc.get(_cal.service_id, [])
        _nur = [
            _aux_sets.get(_c.aux_calendar_id, set())
            for _c in _assignments if _c.junction_type == 3
        ]
        if _nur:
            _isect: set[date] = _nur[0]
            for _s in _nur[1:]:
                _isect &= _s
            _eff = (_eff & _isect) | (_isect - _base)
        for _c2 in _assignments:
            _ds = _aux_sets.get(_c2.aux_calendar_id, set())
            if _c2.junction_type == 1:
                _eff |= _ds
            elif _c2.junction_type == 2:
                _eff -= _ds
        _svc_effective[_cal.service_id] = _eff

    active_service_ids: set[str] = {sid for sid, eff in _svc_effective.items() if eff}
    calendars = [c for c in calendars if c.service_id in active_service_ids]
    trips = [t for t in trips if t.service_id is None or t.service_id in active_service_ids]
    trips_by_id = {t.trip_id: t for t in trips}
    trip_ids_set = set(trips_by_id)
    st_rows = [row for row in st_rows if row[0].trip_id in trip_ids_set]

    # Recompute derived sets after filtering
    # Only stops actually used in remaining stop times
    referenced_stop_ids = {row[1].stop_id for row in st_rows}
    # Only shapes still referenced by active trips
    shape_ids_set = {t.shape_id for t in trips if t.shape_id}
    shapes = [s for s in shapes if s.shape_id in shape_ids_set]
    shape_data = {sid: v for sid, v in shape_data.items() if sid in shape_ids_set}
    # Only operators still referenced by active routes
    active_route_ids = {t.route_id for t in trips}
    routes = [r for r in routes if r.route_id in active_route_ids]
    agency_ids_set = {r.agency_id for r in routes if r.agency_id}
    agencies = [a for a in agencies if a.agency_id in agency_ids_set]

    # Pre-compute stops_to_export so it is available for ID map building below.
    stops_to_export = (
        sorted(stops_by_id.values(), key=lambda s: s.stop_id)
        if export_all_stops
        else filter_referenced_stops(stops_by_id, referenced_stop_ids)
    )

    # ── Pre-build validation ────────────────────────────────────────────────────────────
    # Collect all HighPrio validation errors before aborting; only Python exceptions
    # cause an immediate abort (see except block).
    validation_errors: list[ExportEvent] = []

    if service_ids_set and not active_service_ids:
        evt = _log("HighPrio", "no_valid_calendar_days")
        yield evt
        validation_errors.append(evt)

    # Warn about trips without an assigned route path (only relevant when shapes are exported)
    if export_shapes:
        for t in trips:
            if not t.shape_id:
                yield _log("MiddlePrio", "trip_no_shape", {"trip_id": t.trip_id})
            elif t.geo_pattern_hash and t.geo_pattern_hash != t.shape_id:
                yield _log("MiddlePrio", "trip_shape_mismatch", {"trip_id": t.trip_id})

    # Warn about trips without an assigned headsign
    for t in trips:
        if not t.trip_headsign_id:
            yield _log("MiddlePrio", "trip_no_headsign", {"trip_id": t.trip_id})

    # ── Build export-ID maps ────────────────────────────────────────────────────────────
    # When prefer_global_ids is True each object's global_id is written instead of the
    # internal ID.  Missing global IDs fall back to the internal ID with a warning;
    # duplicate global IDs within the same object type abort the export.
    agency_id_map: dict[str, str] = {}  # internal → exported ID
    route_id_map:  dict[str, str] = {}
    stop_id_map:   dict[str, str] = {}
    trip_id_map:   dict[str, str] = {}

    if prefer_global_ids:
        agency_id_map, evts, errs = _build_export_id_map(
            agencies,
            lambda a: a.agency_id, lambda a: a.global_id,
            "global_id_missing_agency", "agency_id", "global_id_duplicate_agency",
        )
        for e in evts:
            yield e
        validation_errors.extend(errs)

        route_id_map, evts, errs = _build_export_id_map(
            routes,
            lambda r: r.route_id, lambda r: r.global_id,
            "global_id_missing_route", "route_id", "global_id_duplicate_route",
        )
        for e in evts:
            yield e
        validation_errors.extend(errs)

        # stops (includes parent stations via filter_referenced_stops)
        stop_id_map, evts, errs = _build_export_id_map(
            stops_to_export,
            lambda s: s.stop_id, lambda s: s.global_id,
            "global_id_missing_stop", "stop_id", "global_id_duplicate_stop",
        )
        for e in evts:
            yield e
        validation_errors.extend(errs)

        trip_id_map, evts, errs = _build_export_id_map(
            trips,
            lambda t: t.trip_id, lambda t: t.global_id,
            "global_id_missing_trip", "trip_id", "global_id_duplicate_trip",
        )
        for e in evts:
            yield e
        validation_errors.extend(errs)
    else:
        # Identity maps — no transformation
        for a in agencies:
            agency_id_map[a.agency_id] = a.agency_id
        for r in routes:
            route_id_map[r.route_id] = r.route_id
        for s in stops_to_export:
            stop_id_map[s.stop_id] = s.stop_id
        for t in trips:
            trip_id_map[t.trip_id] = t.trip_id

    # Build short shape ID mapping (8-char CRC32 hex), with salt-based collision resolution
    shape_id_map: dict[str, str] = {}  # original shape_id → short shape_id
    _short_to_orig: dict[str, str] = {}
    for _sid in sorted(shape_ids_set):  # sorted for determinism
        _short = _shorten_shape_id(_sid)
        _salt = 0
        while _short in _short_to_orig:
            _salt += 1
            _short = _shorten_shape_id(f"{_sid}\x00{_salt}")
            logger.warning("Shape ID CRC32 collision for %s (resolved with salt %d)", _sid, _salt)
        _short_to_orig[_short] = _sid
        shape_id_map[_sid] = _short

    yield _log("Info", "trips_found", {"count": len(trips)})

    if validation_errors:
        yield _log("HighPrio", "export_aborted", status="error")
        return

    # ------------------------------------------------------------------
    # Build ZIP archive
    # ------------------------------------------------------------------
    zip_buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:

            # ── agency.txt ──────────────────────────────────────────
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([
                "agency_id", "agency_name", "agency_url", "agency_timezone",
                "agency_lang", "agency_phone", "agency_fare_url", "agency_email",
            ])
            for a in agencies:
                w.writerow([
                    agency_id_map.get(a.agency_id, a.agency_id),
                    a.agency_name, a.agency_url, a.agency_timezone,
                    a.agency_lang or "", a.agency_phone or "",
                    a.agency_fare_url or "", a.agency_email or "",
                ])
            zf.writestr("agency.txt", buf.getvalue())

            # ── routes.txt ──────────────────────────────────────────
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([
                "route_id", "agency_id", "route_short_name", "route_long_name",
                "route_desc", "route_type", "route_url", "route_color",
                "route_text_color", "route_sort_order",
                "continuous_pickup", "continuous_drop_off", "network_id",
            ])
            # Sort by existing route_sort_order (nulls last, then by route_id),
            # then re-index from 1 so the exported values are contiguous.
            routes_sorted = sorted(
                routes,
                key=lambda r: (r.route_sort_order is None, r.route_sort_order or 0, r.route_id),
            )
            for new_order, r in enumerate(routes_sorted, start=1):
                w.writerow([
                    route_id_map.get(r.route_id, r.route_id),
                    agency_id_map.get(r.agency_id, r.agency_id) if r.agency_id else "",
                    r.route_short_name or "", r.route_long_name or "",
                    r.route_desc or "", r.route_type,
                    r.route_url or "", r.route_color or "", r.route_text_color or "",
                    str(new_order),
                    "" if r.continuous_pickup is None else str(r.continuous_pickup),
                    "" if r.continuous_drop_off is None else str(r.continuous_drop_off),
                    r.network_id or "",
                ])
            zf.writestr("routes.txt", buf.getvalue())

            # ── calendar.txt ─────────────────────────────────────────
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([
                "service_id", "monday", "tuesday", "wednesday", "thursday",
                "friday", "saturday", "sunday", "start_date", "end_date",
            ])
            for c in calendars:
                # Trim validity bounds to the export period
                eff = _svc_effective.get(c.service_id, set())
                cs = max(c.start_date, date_from)
                ce = min(c.end_date, date_to)
                if cs > ce:
                    # No overlap in base pattern – derive bounds from effective dates
                    cs = min(eff) if eff else date_from
                    ce = max(eff) if eff else date_to
                w.writerow([
                    c.service_id,
                    c.monday, c.tuesday, c.wednesday, c.thursday,
                    c.friday, c.saturday, c.sunday,
                    cs.strftime("%Y%m%d"),
                    ce.strftime("%Y%m%d"),
                ])
            zf.writestr("calendar.txt", buf.getvalue())

            # ── calendar_dates.txt ───────────────────────────────────
            cal_exceptions = compute_calendar_exceptions(
                calendars, cac_rows, aux_dates_by_aux_cal, date_from, date_to
            )
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["service_id", "date", "exception_type"])
            for svc_id, dt, exc_type in cal_exceptions:
                w.writerow([svc_id, dt.strftime("%Y%m%d"), exc_type])
            zf.writestr("calendar_dates.txt", buf.getvalue())

            # ── shapes.txt ───────────────────────────────────────────
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([
                "shape_id", "shape_pt_lat", "shape_pt_lon",
                "shape_pt_sequence", "shape_dist_traveled",
            ])
            shape_pts_count = 0
            if export_shapes:
                for sh in shapes:
                    if sh.shape_id not in shape_data:
                        continue
                    pts, cum = shape_data[sh.shape_id]
                    for seq, ((plat, plon), dist) in enumerate(zip(pts, cum), start=1):
                        w.writerow([
                            shape_id_map.get(sh.shape_id, sh.shape_id),
                            f"{plat:.6f}", f"{plon:.6f}",
                            seq,
                            f"{dist:.2f}",
                        ])
                        shape_pts_count += 1
            zf.writestr("shapes.txt", buf.getvalue())

            # ── trips.txt ────────────────────────────────────────────
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([
                "route_id", "service_id", "trip_id", "trip_headsign",
                "trip_short_name", "direction_id", "block_id", "shape_id",
                "wheelchair_accessible", "bikes_allowed",
            ])
            for t in trips:
                w.writerow([
                    route_id_map.get(t.route_id, t.route_id),
                    t.service_id or "",
                    trip_id_map.get(t.trip_id, t.trip_id),
                    headsign_map.get(t.trip_headsign_id, "") if t.trip_headsign_id else "",
                    t.trip_short_name or "",
                    "" if t.direction_id is None else str(t.direction_id),
                    t.block_id or "",
                    (shape_id_map.get(t.shape_id, t.shape_id) if t.shape_id else "") if export_shapes else "",
                    "" if t.wheelchair_accessible is None else str(t.wheelchair_accessible),
                    "" if t.bikes_allowed is None else str(t.bikes_allowed),
                ])
            zf.writestr("trips.txt", buf.getvalue())

            # ── stops.txt ────────────────────────────────────────────
            # stops_to_export was pre-computed before validation (needed for ID map building).
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([
                "stop_id", "stop_code", "stop_name", "tts_stop_name",
                "stop_desc", "stop_lat", "stop_lon", "zone_id", "stop_url",
                "location_type", "parent_station", "stop_timezone",
                "wheelchair_boarding", "level_id", "platform_code",
            ])
            for s in stops_to_export:
                w.writerow([
                    stop_id_map.get(s.stop_id, s.stop_id),
                    s.stop_code or "",
                    s.stop_name or "", s.tts_stop_name or "",
                    s.stop_desc or "",
                    f"{s.stop_lat:.6f}" if s.stop_lat is not None else "",
                    f"{s.stop_lon:.6f}" if s.stop_lon is not None else "",
                    s.zone_id or "", s.stop_url or "",
                    "" if s.location_type is None else str(s.location_type),
                    stop_id_map.get(s.parent_station, s.parent_station) if s.parent_station else "",
                    s.stop_timezone or "",
                    "" if s.wheelchair_boarding is None else str(s.wheelchair_boarding),
                    s.level_id or "", s.platform_code or "",
                ])
            zf.writestr("stops.txt", buf.getvalue())

            # ── stop_times.txt ───────────────────────────────────────
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([
                "trip_id", "arrival_time", "departure_time", "stop_id",
                "stop_sequence", "stop_headsign", "pickup_type", "drop_off_type",
                "continuous_pickup", "continuous_drop_off",
                "shape_dist_traveled", "timepoint",
            ])
            st_count = 0
            _seq_trip_id: str | None = None
            _seq_counter: int = 0
            _prev_shape_dist: float = 0.0  # monotone lower bound per trip
            for row in st_rows:
                st: StopTime = row[0]
                rbs: RouteBandStop = row[1]
                if st.trip_id != _seq_trip_id:
                    _seq_trip_id = st.trip_id
                    _seq_counter = 0
                    _prev_shape_dist = 0.0
                _seq_counter += 1

                trip = trips_by_id.get(st.trip_id)
                if export_shapes and trip and trip.shape_id and trip.shape_id in shape_data:
                    stop = stops_by_id.get(rbs.stop_id)
                    if stop and stop.stop_lat is not None and stop.stop_lon is not None:
                        pts, cum = shape_data[trip.shape_id]
                        sdt = _project_stop_on_shape(
                            stop.stop_lat, stop.stop_lon, pts, cum, _prev_shape_dist
                        )
                        _prev_shape_dist = sdt
                        sdt_str = f"{sdt:.2f}"
                    else:
                        sdt_str = f"{st.shape_dist_traveled:.2f}" if st.shape_dist_traveled is not None else ""
                else:
                    sdt_str = "" if not export_shapes else (
                        f"{st.shape_dist_traveled:.2f}" if st.shape_dist_traveled is not None else ""
                    )

                dep = _format_gtfs_time(st.departure_time)
                arr = _format_gtfs_time(st.arrival_time) or dep  # GTFS: arrival must not be empty

                w.writerow([
                    trip_id_map.get(st.trip_id, st.trip_id), arr, dep,
                    stop_id_map.get(rbs.stop_id, rbs.stop_id), _seq_counter,
                    headsign_map.get(st.stop_headsign_id, "") if st.stop_headsign_id else "",
                    "" if st.pickup_type is None else str(st.pickup_type),
                    "" if st.drop_off_type is None else str(st.drop_off_type),
                    "" if st.continuous_pickup is None else str(st.continuous_pickup),
                    "" if st.continuous_drop_off is None else str(st.continuous_drop_off),
                    sdt_str,
                    "" if st.timepoint is None else str(st.timepoint),
                ])
                st_count += 1
            zf.writestr("stop_times.txt", buf.getvalue())

    except Exception as exc:  # noqa: BLE001
        logger.exception("GTFS export for version %s failed", version_id)
        yield _log("HighPrio", "internal_error", {"detail": str(exc)}, "error")
        return

    # ------------------------------------------------------------------
    # Return ZIP as Base64 in the done event
    # ------------------------------------------------------------------
    zip_b64 = base64.b64encode(zip_buffer.getvalue()).decode("ascii")
    export_filename = f"gtfs_export_{uuid.uuid4()}.zip"
    yield {
        "level": "Info",
        "key": "export_success",
        "params": {},
        "status": "done",
        "payload": zip_b64,
        "filename": export_filename,
    }
