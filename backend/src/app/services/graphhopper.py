"""GraphHopper adapter — thin wrapper around the local GraphHopper Route API.

This module encapsulates all direct communication with the GraphHopper
instance.  Callers should use the public async functions ``probe_health()``
and ``route_waypoints()`` as well as the polyline utility ``encode_polyline()``.

Supported GTFS route types
--------------------------
3  (Bus)       →  GraphHopper profile "bus_default"  (PSV-aware routing)
11 (Trolleybus) →  GraphHopper profile "bus_default"

Rail-based types (0=Tram, 1=Metro, 2=Rail, 5=Cable tram, 7=Funicular,
12=Monorail) are listed in ``UNSUPPORTED_GTFS_TYPES`` because GraphHopper's
standard OSM reader does not import railway=* ways.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GH_BASE_URL: str = os.environ.get("GH_BASE_URL", "http://graphhopper:8989").rstrip("/")

# GTFS route_type → GraphHopper profile name.  Extend as more profiles are added.
GTFS_PROFILE: dict[int, str] = {
    3:  "bus_default",   # Bus
    11: "bus_default",   # Trolleybus (road-based)
}

DEFAULT_PROFILE = "car_default"

# All valid GTFS route_type values (extended types 100+ are not validated here).
VALID_GTFS_TYPES: frozenset[int] = frozenset({0, 1, 2, 3, 4, 5, 6, 7, 11, 12})

# Route types for which no routing profile is available.
UNSUPPORTED_GTFS_TYPES: frozenset[int] = frozenset({0, 1, 2, 5, 7, 12})


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class GraphhopperError(Exception):
    """Raised when GraphHopper returns an error or is unreachable."""

    def __init__(self, http_status: int, detail: str) -> None:
        self.http_status = http_status
        super().__init__(detail)


# ---------------------------------------------------------------------------
# Polyline encoding
# ---------------------------------------------------------------------------

def encode_polyline(coords: list[tuple[float, float]]) -> str:
    """Encode ``(lat, lon)`` pairs to a Google Encoded Polyline string."""

    def _encode_value(v: int) -> str:
        v = ~(v << 1) if v < 0 else v << 1
        result = ""
        while v >= 0x20:
            result += chr((0x20 | (v & 0x1F)) + 63)
            v >>= 5
        result += chr(v + 63)
        return result

    output = ""
    prev_lat = prev_lon = 0
    for lat, lon in coords:
        lat_e5 = round(lat * 1e5)
        lon_e5 = round(lon * 1e5)
        output += _encode_value(lat_e5 - prev_lat)
        output += _encode_value(lon_e5 - prev_lon)
        prev_lat = lat_e5
        prev_lon = lon_e5
    return output


# ---------------------------------------------------------------------------
# Blocking helpers (intended to be run via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _probe_health_sync() -> bool:
    """Return True if the local GraphHopper instance is reachable."""
    url = f"{GH_BASE_URL}/health"
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def _call_route_sync(
    profile: str,
    waypoints: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """POST a route request to GraphHopper and return ``(lat, lon)`` tuples."""
    payload: dict = {
        "profile": profile,
        "points": [[lon, lat] for lat, lon in waypoints],  # GH expects [lng, lat]
        "points_encoded": False,
    }

    url = f"{GH_BASE_URL}/route"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    logger.info(
        "GraphHopper request: POST %s  profile=%s  points=%d  payload=%s",
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
            "GraphHopper HTTP error: status=%d  url=%s  response_body=%s",
            exc.code,
            url,
            detail_body,
        )
        raise GraphhopperError(exc.code, detail_body) from exc
    except urllib.error.URLError as exc:
        logger.error("GraphHopper connection error: url=%s  reason=%s", url, exc.reason)
        raise GraphhopperError(502, f"Could not reach GraphHopper: {exc.reason}") from exc

    try:
        coords = body["paths"][0]["points"]["coordinates"]
    except (KeyError, IndexError) as exc:
        logger.error("GraphHopper unexpected response structure: %s", json.dumps(body))
        raise GraphhopperError(
            502, f"Unexpected GraphHopper response structure: {body}"
        ) from exc

    logger.info("GraphHopper response: %d route points received", len(coords))
    # GH returns [lng, lat, (ele)]
    return [(c[1], c[0]) for c in coords]


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------

async def probe_health() -> bool:
    """Return True if the local GraphHopper instance is reachable."""
    return await asyncio.to_thread(_probe_health_sync)


async def route_waypoints(
    route_type: int,
    waypoints: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Route *waypoints* via GraphHopper using the profile for *route_type*.

    Parameters
    ----------
    route_type:
        GTFS route_type integer (e.g. 3 for Bus).
    waypoints:
        Sequence of ``(lat, lon)`` tuples — at least two points required.

    Returns
    -------
    list[tuple[float, float]]
        ``(lat, lon)`` tuples along the routed path.

    Raises
    ------
    GraphhopperError
        If GraphHopper returns an error or is unreachable.
    """
    profile = GTFS_PROFILE.get(route_type, DEFAULT_PROFILE)
    return await asyncio.to_thread(_call_route_sync, profile, waypoints)
