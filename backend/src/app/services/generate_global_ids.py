"""Generate global IDs for trips by resolving a preset template.

Placeholders (case-sensitive, enclosed in curly braces):
  {AgencyId}        â€” agency_id of the agency assigned to the trip's route
  {AgencyGlobalId}  â€” global_id of the agency
  {LineId}          â€” route_id of the trip's route
  {LineGlobalId}    â€” global_id of the route
  {DayTypeId}       â€” service_id of the trip
  {TripShortName}   â€” trip_short_name of the trip
  {GeneratedNumber} â€” random 6-digit number (zero-padded, unique per trip)
  {UUID}            â€” deterministic UUID-5 derived from the trip_id

Every placeholder that references optional data is validated before any ID is
written.  If a required value is missing a :exc:`GlobalIdResolutionError` is
raised and *no* trips are modified.
"""
from __future__ import annotations

import random
import uuid
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agency, Route, Trip

_NAMESPACE = uuid.NAMESPACE_OID


class GlobalIdResolutionError(Exception):
    """Raised when a preset placeholder cannot be resolved due to missing data.

    Carries a machine-readable *error_code* and optional *params* for
    structured API error responses that the frontend can localize.
    """

    def __init__(self, error_code: str, **params: object) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.params: dict[str, object] = dict(params)


class GlobalIdResult(NamedTuple):
    updated: int
    skipped: int


def _check_placeholders(
    preset: str,
    *,
    route: Route | None,
    agency: Agency | None,
    agency_id_val: str,
    trips_to_update: list[Trip],
) -> None:
    """Verify that every placeholder used in *preset* can be resolved.

    Raises :exc:`GlobalIdResolutionError` with a machine-readable error code
    on the first unresolvable placeholder found.  Must be called *before* any
    database writes.
    """
    needs_agency = "{AgencyId}" in preset or "{AgencyGlobalId}" in preset

    if needs_agency:
        if not agency_id_val:
            ph = "{AgencyId}" if "{AgencyId}" in preset else "{AgencyGlobalId}"
            raise GlobalIdResolutionError("global_id_no_agency", placeholder=ph)
        if agency is None:
            raise GlobalIdResolutionError(
                "global_id_agency_not_found", agency_id=agency_id_val
            )

    if "{AgencyGlobalId}" in preset:
        if not (agency.global_id or "").strip():  # type: ignore[union-attr]
            raise GlobalIdResolutionError(
                "global_id_agency_no_global_id", agency_id=agency_id_val
            )

    if "{LineId}" in preset and route is None:
        raise GlobalIdResolutionError("global_id_route_not_found", placeholder="{LineId}")

    if "{LineGlobalId}" in preset:
        if route is None:
            raise GlobalIdResolutionError(
                "global_id_route_not_found", placeholder="{LineGlobalId}"
            )
        if not (route.global_id or "").strip():
            raise GlobalIdResolutionError(
                "global_id_route_no_global_id", route_id=route.route_id
            )

    if "{DayTypeId}" in preset:
        missing = sum(1 for t in trips_to_update if not (t.service_id or "").strip())
        if missing:
            raise GlobalIdResolutionError("global_id_trips_missing_day_type", count=missing)

    if "{TripShortName}" in preset:
        missing = sum(1 for t in trips_to_update if not (t.trip_short_name or "").strip())
        if missing:
            raise GlobalIdResolutionError("global_id_trips_missing_short_name", count=missing)


def _resolve(
    preset: str,
    *,
    agency_id: str,
    agency_global_id: str,
    line_id: str,
    line_global_id: str,
    day_type_id: str,
    trip_short_name: str,
    trip_id: str,
) -> str:
    """Resolve all placeholders in *preset* for a single trip."""
    number = f"{random.randint(0, 999_999):06d}"
    deterministic_uuid = str(uuid.uuid5(_NAMESPACE, trip_id))
    return (
        preset
        .replace("{AgencyId}", agency_id)
        .replace("{AgencyGlobalId}", agency_global_id)
        .replace("{LineId}", line_id)
        .replace("{LineGlobalId}", line_global_id)
        .replace("{DayTypeId}", day_type_id)
        .replace("{TripShortName}", trip_short_name)
        .replace("{GeneratedNumber}", number)
        .replace("{UUID}", deterministic_uuid)
    )


async def generate_global_ids(
    *,
    version_id: uuid.UUID,
    route_id: str,
    trip_ids: list[str],
    preset: str,
    overwrite: bool,
    session: AsyncSession,
) -> GlobalIdResult:
    """Assign resolved global IDs to the specified trips.

    For each trip in *trip_ids*:
    - If ``overwrite`` is False and the trip already has a ``global_id``, it
      is counted as skipped.
    - Otherwise the preset is validated and resolved; if any placeholder
      cannot be resolved a :exc:`GlobalIdResolutionError` is raised and
      *no* trips are modified.

    Returns a :class:`GlobalIdResult` named tuple with ``updated`` and
    ``skipped`` counts.
    """
    if not trip_ids:
        return GlobalIdResult(updated=0, skipped=0)

    # Load matching trips
    trips_result = await session.execute(
        select(Trip).where(
            Trip.version_id == version_id,
            Trip.route_id == route_id,
            Trip.trip_id.in_(trip_ids),
        )
    )
    trips = list(trips_result.scalars().all())

    if not trips:
        return GlobalIdResult(updated=0, skipped=len(trip_ids))

    # Determine which trips will actually be written
    trips_to_update = [t for t in trips if overwrite or not t.global_id]
    skipped = len(trips) - len(trips_to_update)

    if not trips_to_update:
        return GlobalIdResult(updated=0, skipped=skipped)

    # Load the route to resolve line-level placeholders
    route_result = await session.execute(
        select(Route).where(
            Route.version_id == version_id,
            Route.route_id == route_id,
        )
    )
    route = route_result.scalar_one_or_none()
    line_id = (route.route_id if route else "") or ""
    line_global_id = ((route.global_id if route else "") or "")
    agency_id_val = ((route.agency_id if route else "") or "")

    # Load the agency if the route has one
    agency: Agency | None = None
    if agency_id_val:
        agency_result = await session.execute(
            select(Agency).where(
                Agency.version_id == version_id,
                Agency.agency_id == agency_id_val,
            )
        )
        agency = agency_result.scalar_one_or_none()

    agency_id = (agency.agency_id if agency else "") or ""
    agency_global_id = ((agency.global_id if agency else "") or "")

    # Validate before any writes – raises GlobalIdResolutionError on failure
    _check_placeholders(
        preset,
        route=route,
        agency=agency,
        agency_id_val=agency_id_val,
        trips_to_update=trips_to_update,
    )

    for trip in trips_to_update:
        trip.global_id = _resolve(
            preset,
            agency_id=agency_id,
            agency_global_id=agency_global_id,
            line_id=line_id,
            line_global_id=line_global_id,
            day_type_id=trip.service_id or "",
            trip_short_name=trip.trip_short_name or "",
            trip_id=trip.trip_id,
        )

    await session.commit()
    return GlobalIdResult(updated=len(trips_to_update), skipped=skipped)

