"""Unit tests for app.services.reroute_shapes.

Covered functions:
* reroute_shapes_by_ids  — empty-list fast-path, no-shapes-found path
* cleanup_free_coords_around_gaps — pure control-flow logic for identifying
  and deleting orphaned free-coordinate intermediate points

All tests use AsyncMock sessions; no real database is needed.
"""

import tests.test_config  # noqa: F401 — must be first; sets env vars

import types
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, call

from app.services.reroute_shapes import (
    cleanup_free_coords_around_gaps,
    reroute_shapes_by_ids,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pt(*, stop_id=None, sort_order: float = 1.0):
    """Return a minimal fake ShapeIntermediatePoint-like object."""
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        stop_id=stop_id,
        sort_order=sort_order,
    )


def _make_session_with_pts(pts: list) -> AsyncMock:
    """Return an AsyncMock session whose execute() returns *pts* via .scalars().all()."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = pts
    session.execute = AsyncMock(return_value=result_mock)
    return session


# ---------------------------------------------------------------------------
# reroute_shapes_by_ids
# ---------------------------------------------------------------------------

class TestRerouteShapesByIds(unittest.IsolatedAsyncioTestCase):
    """Tests for the fast-paths in reroute_shapes_by_ids."""

    async def test_empty_list_yields_done_total_zero(self):
        session = AsyncMock()
        events = []
        async for e in reroute_shapes_by_ids(uuid.uuid4(), [], session):
            events.append(e)
        self.assertEqual(events, [{"type": "done", "total": 0}])

    async def test_empty_list_does_not_touch_session(self):
        session = AsyncMock()
        async for _ in reroute_shapes_by_ids(uuid.uuid4(), [], session):
            pass
        session.execute.assert_not_called()

    async def test_no_autoroute_shapes_found_yields_done_total_zero(self):
        """When the DB query returns no shapes, done is yielded immediately."""
        session = _make_session_with_pts([])  # .scalars().all() → []
        events = []
        async for e in reroute_shapes_by_ids(uuid.uuid4(), ["shape_a"], session):
            events.append(e)
        self.assertEqual(events, [{"type": "done", "total": 0}])

    async def test_no_autoroute_shapes_found_yields_exactly_one_event(self):
        session = _make_session_with_pts([])
        events = []
        async for e in reroute_shapes_by_ids(uuid.uuid4(), ["shape_a", "shape_b"], session):
            events.append(e)
        self.assertEqual(len(events), 1)


# ---------------------------------------------------------------------------
# cleanup_free_coords_around_gaps
# ---------------------------------------------------------------------------

class TestCleanupFreeCoordsAroundGaps(unittest.IsolatedAsyncioTestCase):
    """Tests for cleanup_free_coords_around_gaps."""

    async def test_empty_gaps_does_not_call_session(self):
        session = AsyncMock()
        await cleanup_free_coords_around_gaps(uuid.uuid4(), {}, session)
        session.execute.assert_not_called()

    async def test_empty_gaps_returns_none(self):
        session = AsyncMock()
        result = await cleanup_free_coords_around_gaps(uuid.uuid4(), {}, session)
        self.assertIsNone(result)

    # --- Sequences with no free-coord runs → no DELETE ---

    async def test_all_stop_refs_no_delete_called(self):
        """A sequence of only stop-reference points has no free-coord runs."""
        pts = [
            _pt(stop_id="A", sort_order=1.0),
            _pt(stop_id="B", sort_order=2.0),
            _pt(stop_id="C", sort_order=3.0),
        ]
        session = _make_session_with_pts(pts)
        await cleanup_free_coords_around_gaps(uuid.uuid4(), {"s1": [0.5]}, session)
        # Only the SELECT is executed; no DELETE
        self.assertEqual(session.execute.call_count, 1)

    async def test_empty_points_sequence_no_delete_called(self):
        """When all intermediate points are already gone, nothing is deleted."""
        session = _make_session_with_pts([])
        await cleanup_free_coords_around_gaps(uuid.uuid4(), {"s1": [1.0]}, session)
        self.assertEqual(session.execute.call_count, 1)

    async def test_free_coord_between_two_stops_not_deleted(self):
        """A free-coord run sandwiched between two stop-references stays."""
        pts = [
            _pt(stop_id="A", sort_order=1.0),
            _pt(stop_id=None, sort_order=2.0),   # free — between stops
            _pt(stop_id="B", sort_order=3.0),
        ]
        session = _make_session_with_pts(pts)
        await cleanup_free_coords_around_gaps(uuid.uuid4(), {"s1": [2.0]}, session)
        self.assertEqual(session.execute.call_count, 1)

    async def test_multiple_free_coords_between_stops_not_deleted(self):
        """Multiple consecutive free-coords between stops are all kept."""
        pts = [
            _pt(stop_id="A", sort_order=1.0),
            _pt(stop_id=None, sort_order=2.0),
            _pt(stop_id=None, sort_order=3.0),
            _pt(stop_id="B", sort_order=4.0),
        ]
        session = _make_session_with_pts(pts)
        await cleanup_free_coords_around_gaps(uuid.uuid4(), {"s1": [2.0]}, session)
        self.assertEqual(session.execute.call_count, 1)

    # --- Dangling free-coord runs → SELECT + DELETE ---

    async def test_free_coord_at_start_triggers_delete(self):
        """A free-coord point before the first stop-reference must be deleted."""
        pts = [
            _pt(stop_id=None, sort_order=1.0),
            _pt(stop_id="A",  sort_order=2.0),
        ]
        session = _make_session_with_pts(pts)
        await cleanup_free_coords_around_gaps(uuid.uuid4(), {"s1": [1.0]}, session)
        self.assertEqual(session.execute.call_count, 2)

    async def test_free_coord_at_end_triggers_delete(self):
        """A free-coord point after the last stop-reference must be deleted."""
        pts = [
            _pt(stop_id="A",  sort_order=1.0),
            _pt(stop_id=None, sort_order=2.0),
        ]
        session = _make_session_with_pts(pts)
        await cleanup_free_coords_around_gaps(uuid.uuid4(), {"s1": [2.0]}, session)
        self.assertEqual(session.execute.call_count, 2)

    async def test_multiple_free_coords_at_start_triggers_delete(self):
        pts = [
            _pt(stop_id=None, sort_order=1.0),
            _pt(stop_id=None, sort_order=2.0),
            _pt(stop_id="A",  sort_order=3.0),
        ]
        session = _make_session_with_pts(pts)
        await cleanup_free_coords_around_gaps(uuid.uuid4(), {"s1": [1.0]}, session)
        self.assertEqual(session.execute.call_count, 2)

    async def test_multiple_free_coords_at_end_triggers_delete(self):
        pts = [
            _pt(stop_id="A",  sort_order=1.0),
            _pt(stop_id=None, sort_order=2.0),
            _pt(stop_id=None, sort_order=3.0),
        ]
        session = _make_session_with_pts(pts)
        await cleanup_free_coords_around_gaps(uuid.uuid4(), {"s1": [2.0]}, session)
        self.assertEqual(session.execute.call_count, 2)

    async def test_entire_sequence_is_free_coords_triggers_delete(self):
        """All-free-coord sequence is entirely dangling (no prev/next stop)."""
        pts = [
            _pt(stop_id=None, sort_order=1.0),
            _pt(stop_id=None, sort_order=2.0),
        ]
        session = _make_session_with_pts(pts)
        await cleanup_free_coords_around_gaps(uuid.uuid4(), {"s1": [1.0]}, session)
        self.assertEqual(session.execute.call_count, 2)

    async def test_single_free_coord_only_triggers_delete(self):
        pts = [_pt(stop_id=None, sort_order=1.0)]
        session = _make_session_with_pts(pts)
        await cleanup_free_coords_around_gaps(uuid.uuid4(), {"s1": [1.0]}, session)
        self.assertEqual(session.execute.call_count, 2)

    # --- Mixed leading + trailing free-coord runs ---

    async def test_free_coords_at_both_ends_triggers_delete(self):
        """Free-coord runs at both start and end should both be marked for deletion."""
        pts = [
            _pt(stop_id=None, sort_order=1.0),  # dangling start
            _pt(stop_id="A",  sort_order=2.0),
            _pt(stop_id="B",  sort_order=3.0),
            _pt(stop_id=None, sort_order=4.0),  # dangling end
        ]
        session = _make_session_with_pts(pts)
        await cleanup_free_coords_around_gaps(uuid.uuid4(), {"s1": [1.0]}, session)
        self.assertEqual(session.execute.call_count, 2)

    # --- Multiple shapes ---

    async def test_multiple_shapes_each_triggers_select(self):
        """Each shape in gaps triggers its own SELECT query."""
        pts_no_free = [_pt(stop_id="A", sort_order=1.0)]
        session = _make_session_with_pts(pts_no_free)
        await cleanup_free_coords_around_gaps(
            uuid.uuid4(),
            {"s1": [0.5], "s2": [0.5], "s3": [0.5]},
            session,
        )
        # 3 shapes → at least 3 SELECT calls; no DELETE since no dangling free-coords
        self.assertGreaterEqual(session.execute.call_count, 3)

    async def test_multiple_shapes_one_needs_delete(self):
        """Only the shape with a dangling free-coord issues a DELETE."""
        clean_pts = [_pt(stop_id="A", sort_order=1.0)]
        dirty_pts = [_pt(stop_id=None, sort_order=1.0)]

        call_count = 0

        async def execute_side_effect(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            # Alternate: first shape gets clean_pts, second gets dirty_pts
            if call_count == 1:
                result.scalars.return_value.all.return_value = clean_pts
            elif call_count == 2:
                result.scalars.return_value.all.return_value = dirty_pts
            else:
                result.scalars.return_value.all.return_value = []
            return result

        session = AsyncMock()
        session.execute.side_effect = execute_side_effect

        await cleanup_free_coords_around_gaps(
            uuid.uuid4(),
            {"s1": [0.5], "s2": [1.0]},
            session,
        )
        # 2 SELECT + 1 DELETE (only for s2 which has the dangling free-coord)
        self.assertEqual(session.execute.call_count, 3)


if __name__ == "__main__":
    unittest.main()
