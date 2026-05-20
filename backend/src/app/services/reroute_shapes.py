"""Re-routing service for shapes affected by a platform coordinate change or deletion.

When a platform (Steig, location_type=0) is moved or deleted, every shape
that:

  * references the platform as an intermediate point, AND
  * has ``is_autoroute_active = True``

must be re-routed so that its ``routed_polyline`` stays up-to-date.

Public API
----------
``collect_affected_shape_ids(version_id, platform_stop_ids, session)``
    Return the IDs of all affected auto-route shapes (call BEFORE deletion so
    the intermediate-point rows still exist in the database).

``reroute_shapes_by_ids(version_id, shape_ids, session)``
    Async generator — re-routes shapes by explicit ID list.  Shapes are loaded
    fresh from the database, so any cascade-deleted intermediate points are
    already absent.

``reroute_shapes_for_platform(version_id, platform_stop_id, session)``
    Convenience wrapper used by the PUT (position-change) flow: collects the
    affected IDs and delegates to ``reroute_shapes_by_ids``.

SSE event schema
----------------
Each yielded dict is one of:

  {"type": "progress", "current": int, "total": int,
   "shape_id": str, "shape_name": str | None}

  {"type": "done", "total": int}

  {"type": "error", "message": str}
"""
from __future__ import annotations

import logging
import uuid
from typing import AsyncGenerator

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Shape, ShapeIntermediatePoint, Stop
from app.services.graphhopper import (
    GraphhopperError,
    UNSUPPORTED_GTFS_TYPES,
    encode_polyline,
    route_waypoints,
)

logger = logging.getLogger(__name__)


async def collect_deletion_context(
    version_id: uuid.UUID,
    platform_stop_ids: list[str],
    session: AsyncSession,
) -> tuple[list[str], dict[str, list[float]]]:
    """Collect affected shape IDs and deletion-gap info for the delete flow.

    Must be called **before** the platforms are deleted.

    Returns:
        shape_ids: IDs of affected auto-route shapes (deduplicated, stable order)
        gaps:      mapping of shape_id → list of sort_orders of the intermediate
                   points being deleted (used by ``cleanup_free_coords_around_gaps``)
    """
    if not platform_stop_ids:
        return [], {}
    rows = (await session.execute(
        select(Shape.shape_id, ShapeIntermediatePoint.sort_order)
        .join(
            ShapeIntermediatePoint,
            (ShapeIntermediatePoint.version_id == Shape.version_id) &
            (ShapeIntermediatePoint.shape_id == Shape.shape_id),
        )
        .where(
            ShapeIntermediatePoint.version_id == version_id,
            ShapeIntermediatePoint.stop_id.in_(platform_stop_ids),
            Shape.is_autoroute_active.is_(True),
        )
    )).all()

    shape_ids: list[str] = []
    gaps: dict[str, list[float]] = {}
    seen: set[str] = set()
    for shape_id, sort_order in rows:
        if shape_id not in seen:
            shape_ids.append(shape_id)
            seen.add(shape_id)
        gaps.setdefault(shape_id, []).append(sort_order)
    return shape_ids, gaps


async def collect_affected_shape_ids(
    version_id: uuid.UUID,
    platform_stop_ids: list[str],
    session: AsyncSession,
) -> list[str]:
    """Return IDs of all auto-route shapes that reference any of *platform_stop_ids*.

    Must be called **before** the platforms are deleted so that the
    intermediate-point rows are still present in the database.

    .. note::
       For the deletion flow prefer ``collect_deletion_context`` which also
       captures the gap sort-orders needed for free-coord cleanup.
    """
    shape_ids, _ = await collect_deletion_context(version_id, platform_stop_ids, session)
    return shape_ids


async def cleanup_free_coords_around_gaps(
    version_id: uuid.UUID,
    gaps: dict[str, list[float]],
    session: AsyncSession,
) -> None:
    """Delete orphaned free-coordinate intermediate points after a stop deletion.

    For each shape in *gaps*, loads its remaining intermediate points (after the
    deletion cascade has been committed) and removes any contiguous run of
    free-coordinate points (``stop_id IS NULL``) that is:

    * at the **beginning** of the sequence (no stop reference before it),
    * at the **end** of the sequence (no stop reference after it), or
    * **spanning a deletion gap** — i.e. the sort_order of a deleted
      intermediate point lies between the bounding stop references of the run.

    Does **not** commit; the caller is responsible for committing.
    Only applies to ``is_autoroute_active = True`` shapes (guaranteed by
    ``collect_deletion_context``).
    """
    if not gaps:
        return

    for shape_id, deleted_sort_orders in gaps.items():
        # Reload points after cascade — stop-reference rows are already gone
        pts = (await session.execute(
            select(ShapeIntermediatePoint)
            .where(
                ShapeIntermediatePoint.version_id == version_id,
                ShapeIntermediatePoint.shape_id == shape_id,
            )
            .order_by(ShapeIntermediatePoint.sort_order)
        )).scalars().all()

        ids_to_delete: list[uuid.UUID] = []
        i = 0
        while i < len(pts):
            if pts[i].stop_id is not None:
                i += 1
                continue

            # Collect the entire contiguous free-coord run
            run_start = i
            while i < len(pts) and pts[i].stop_id is None:
                i += 1
            run_end = i  # exclusive

            run = pts[run_start:run_end]
            prev_stop = pts[run_start - 1] if run_start > 0 else None
            next_stop = pts[run_end] if run_end < len(pts) else None

            # Case 1: dangling at the beginning or end of the sequence
            if prev_stop is None or next_stop is None:
                ids_to_delete.extend(pt.id for pt in run)
                continue

        if ids_to_delete:
            await session.execute(
                sa_delete(ShapeIntermediatePoint)
                .where(ShapeIntermediatePoint.id.in_(ids_to_delete))
                .execution_options(synchronize_session=False)
            )


async def reroute_shapes_by_ids(
    version_id: uuid.UUID,
    shape_ids: list[str],
    session: AsyncSession,
) -> AsyncGenerator[dict, None]:
    """Yield SSE progress events while re-routing the shapes identified by *shape_ids*.

    Shapes are reloaded fresh from the database, so cascade-deleted intermediate
    points are already absent when this function is called after a deletion.
    """
    if not shape_ids:
        yield {"type": "done", "total": 0}
        return

    rows = (await session.execute(
        select(Shape)
        .where(
            Shape.version_id == version_id,
            Shape.shape_id.in_(shape_ids),
            Shape.is_autoroute_active.is_(True),
        )
        .options(selectinload(Shape.intermediate_points))
    )).scalars().all()

    shapes = list(rows)
    total = len(shapes)

    if total == 0:
        yield {"type": "done", "total": 0}
        return

    # Pre-load all stops referenced by the remaining intermediate points
    all_stop_ids: set[str] = {
        pt.stop_id
        for shape in shapes
        for pt in shape.intermediate_points
        if pt.stop_id
    }
    stops_by_id: dict[str, Stop] = {}
    if all_stop_ids:
        stops_by_id = {
            s.stop_id: s
            for s in (await session.execute(
                select(Stop).where(
                    Stop.version_id == version_id,
                    Stop.stop_id.in_(all_stop_ids),
                )
            )).scalars().all()
        }

    for idx, shape in enumerate(shapes, start=1):
        waypoints: list[tuple[float, float]] = []
        for pt in sorted(shape.intermediate_points, key=lambda p: p.sort_order):
            if pt.stop_id:
                s = stops_by_id.get(pt.stop_id)
                if s and s.stop_lat is not None and s.stop_lon is not None:
                    waypoints.append((s.stop_lat, s.stop_lon))
            elif pt.lat is not None and pt.lon is not None:
                waypoints.append((pt.lat, pt.lon))

        if len(waypoints) < 2:
            logger.warning(
                "Shape %s/%s has fewer than 2 resolvable waypoints — skipping re-route",
                version_id,
                shape.shape_id,
            )
            yield {
                "type": "progress",
                "current": idx,
                "total": total,
                "shape_id": shape.shape_id,
                "shape_name": shape.shape_name,
            }
            continue

        if shape.route_type is not None and shape.route_type in UNSUPPORTED_GTFS_TYPES:
            logger.info(
                "Shape %s/%s has unsupported route_type %d — skipping re-route",
                version_id,
                shape.shape_id,
                shape.route_type,
            )
            yield {
                "type": "progress",
                "current": idx,
                "total": total,
                "shape_id": shape.shape_id,
                "shape_name": shape.shape_name,
            }
            continue

        try:
            routed_coords = await route_waypoints(
                shape.route_type if shape.route_type is not None else 3,
                waypoints,
            )
            shape.routed_polyline = encode_polyline(routed_coords)
            await session.commit()
        except GraphhopperError as exc:
            logger.error(
                "GraphHopper error re-routing shape %s/%s: %s",
                version_id,
                shape.shape_id,
                exc,
            )
            await session.rollback()
            yield {"type": "error", "message": str(exc)}
            return

        yield {
            "type": "progress",
            "current": idx,
            "total": total,
            "shape_id": shape.shape_id,
            "shape_name": shape.shape_name,
        }

    yield {"type": "done", "total": total}


async def reroute_shapes_for_platform(
    version_id: uuid.UUID,
    platform_stop_id: str,
    session: AsyncSession,
) -> AsyncGenerator[dict, None]:
    """Yield SSE progress events while re-routing all auto-route shapes that
    reference *platform_stop_id* as an intermediate point.

    Convenience wrapper used by the PUT (position-change) flow.
    """
    shape_ids = await collect_affected_shape_ids(version_id, [platform_stop_id], session)
    async for event in reroute_shapes_by_ids(version_id, shape_ids, session):
        yield event
