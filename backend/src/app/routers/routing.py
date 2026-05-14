"""Routing — forwards waypoint lists to the local Graphhopper instance and
returns the calculated route polyline.

The local Graphhopper is expected at http://graphhopper:8989 (Docker-internal
hostname).  No external API key is needed.

Supported GTFS route types
--------------------------
3  (Bus)      →  Graphhopper profile "bus"   (PSV-aware, busway + main roads)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, Response, status as http_status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.permissions import Permission, require

router = APIRouter(prefix="/api/route", tags=["routing"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graphhopper base URL — override via env var GH_BASE_URL for testing
# ---------------------------------------------------------------------------

_GH_BASE_URL: str = os.environ.get("GH_BASE_URL", "http://graphhopper:8989").rstrip("/")

# ---------------------------------------------------------------------------
# GTFS route_type → Graphhopper profile name
# Extend this mapping as more profiles are added.
# ---------------------------------------------------------------------------

_GTFS_PROFILE: dict[int, str] = {
    # Road-based profiles
    3: "bus_default",    # Bus
    11: "bus_default",   # Trolleybus (road-based)
    # Rail types (0=Tram, 1=Metro, 2=Rail, 5=Cable tram, 7=Funicular, 12=Monorail)
    # are intentionally absent: Graphhopper's standard OSM reader does not import
    # railway=* ways, so rail routing is not supported.
}

# Used for all route_types not listed in _GTFS_PROFILE.
_DEFAULT_PROFILE = "car_default"

# All valid GTFS route_type values (extended types 100+ are not validated here).
_VALID_GTFS_TYPES: frozenset[int] = frozenset({0, 1, 2, 3, 4, 5, 6, 7, 11, 12})

# Route types for which no routing profile is available.
_UNSUPPORTED_GTFS_TYPES: frozenset[int] = frozenset({0, 1, 2, 5, 7, 12})


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
# Internal exception that carries the upstream HTTP status code
# ---------------------------------------------------------------------------

class _GraphhopperHTTPError(Exception):
    def __init__(self, http_status: int, detail: str) -> None:
        self.http_status = http_status
        super().__init__(detail)


# ---------------------------------------------------------------------------
# Helper: probe Graphhopper health (blocking, run in thread)
# ---------------------------------------------------------------------------

def _probe_graphhopper_health() -> bool:
    """Return True if the local Graphhopper instance is reachable."""
    url = f"{_GH_BASE_URL}/health"
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Helper: call Graphhopper route API (blocking, run in thread)
# ---------------------------------------------------------------------------

def _call_graphhopper(profile: str, waypoints: list[Waypoint]) -> list[RoutePoint]:
    """Send request to the local Graphhopper Route API and decode the response."""
    payload: dict = {
        "profile": profile,
        "points": [[wp.lng, wp.lat] for wp in waypoints],  # GH expects [lng, lat]
        "points_encoded": False,
    }

    url = f"{_GH_BASE_URL}/route"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    logger.info(
        "Graphhopper request: POST %s  profile=%s  points=%d  payload=%s",
        url,
        profile,
        len(waypoints),
        json.dumps(payload),
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail_body = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "Graphhopper HTTP error: status=%d  url=%s  response_body=%s",
            exc.code,
            url,
            detail_body,
        )
        raise _GraphhopperHTTPError(exc.code, detail_body) from exc
    except urllib.error.URLError as exc:
        logger.error("Graphhopper connection error: url=%s  reason=%s", url, exc.reason)
        raise _GraphhopperHTTPError(502, f"Could not reach Graphhopper: {exc.reason}") from exc

    # Parse GeoJSON LineString coordinates from first path
    try:
        coords = body["paths"][0]["points"]["coordinates"]
    except (KeyError, IndexError) as exc:
        logger.error("Graphhopper unexpected response structure: %s", json.dumps(body))
        raise _GraphhopperHTTPError(502, f"Unexpected Graphhopper response structure: {body}") from exc

    logger.info("Graphhopper response: %d route points received", len(coords))
    # GH returns [lng, lat, (ele)]
    return [RoutePoint(lat=c[1], lng=c[0]) for c in coords]


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
    available = await asyncio.to_thread(_probe_graphhopper_health)
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
    if route_type not in _VALID_GTFS_TYPES:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid GTFS route_type: {route_type}. Valid types: {sorted(_VALID_GTFS_TYPES)}",
        )
    if route_type in _UNSUPPORTED_GTFS_TYPES:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Routing is not supported for GTFS route_type {route_type} (rail-based modes require OSM railway track data which is not available in the standard Graphhopper build).",
        )
    profile = _GTFS_PROFILE.get(route_type, _DEFAULT_PROFILE)

    try:
        points = await asyncio.to_thread(_call_graphhopper, profile, body.waypoints)
    except _GraphhopperHTTPError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail=str(exc),
        ) from exc

    return RouteResponse(route_type=route_type, points=points)
