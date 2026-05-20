"""Routing — forwards waypoint lists to the local Graphhopper instance and
returns the calculated route polyline.

The local Graphhopper is expected at http://graphhopper:8989 (Docker-internal
hostname).  No external API key is needed.

GraphHopper communication is handled by ``app.services.graphhopper``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status as http_status
from pydantic import BaseModel, Field

from composegtfs.auth import get_current_user
from composegtfs.permissions import Permission, require
from composegtfs.services.graphhopper import (
    GraphhopperError,
    VALID_GTFS_TYPES,
    UNSUPPORTED_GTFS_TYPES,
    probe_health,
    route_waypoints,
)

router = APIRouter(prefix="/api/route", tags=["routing"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class Waypoint(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lng: float = Field(..., ge=-180.0, le=180.0)


class RouteRequest(BaseModel):
    waypoints: list[Waypoint] = Field(..., min_length=2)


class RoutePoint(BaseModel):
    lat: float
    lng: float


class RouteResponse(BaseModel):
    route_type: int
    points: list[RoutePoint]


class HealthResponse(BaseModel):
    available: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check whether the local Graphhopper instance is reachable",
    dependencies=[require(Permission.SCHEDULE_READ)],
)
async def routing_health(
    _: None = Depends(get_current_user),
) -> HealthResponse:
    available = await probe_health()
    return HealthResponse(available=available)


@router.post(
    "/{route_type}",
    response_model=RouteResponse,
    summary="Calculate a route via local Graphhopper using a GTFS route type",
    dependencies=[require(Permission.SCHEDULE_READ)],
)
async def calculate_route(
    route_type: int,
    body: RouteRequest,
    response: Response,
    _: None = Depends(get_current_user),
) -> RouteResponse:
    if route_type not in VALID_GTFS_TYPES:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid GTFS route_type: {route_type}. Valid types: {sorted(VALID_GTFS_TYPES)}",
        )
    if route_type in UNSUPPORTED_GTFS_TYPES:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Routing is not supported for GTFS route_type {route_type} (rail-based modes require OSM railway track data which is not available in the standard Graphhopper build).",
        )

    waypoints = [(wp.lat, wp.lng) for wp in body.waypoints]
    try:
        coords = await route_waypoints(route_type, waypoints)
    except GraphhopperError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail=str(exc),
        ) from exc

    points = [RoutePoint(lat=lat, lng=lng) for lat, lng in coords]
    return RouteResponse(route_type=route_type, points=points)

