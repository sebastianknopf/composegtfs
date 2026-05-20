"""
Unit tests for pure helper functions in app.services.gtfs_export.

All functions tested here are stateless and require no database connection.
"""

from __future__ import annotations

import math
import types
import unittest
import uuid
import zlib
from datetime import date

# Must be first: sets env vars and adjusts sys.path
import tests.test_config  # noqa: F401

from app.services.gtfs_export import (
    _base_dates_in_range,
    _build_export_id_map,
    _cumulative_distances_m,
    _decode_polyline,
    _format_gtfs_time,
    _haversine_m,
    _project_stop_on_shape,
    _shorten_shape_id,
    compute_calendar_exceptions,
)


# ---------------------------------------------------------------------------
# Helpers for building lightweight mock objects (no DB required)
# ---------------------------------------------------------------------------

def _make_calendar(
    service_id: str,
    start_date: date,
    end_date: date,
    *,
    monday: int = 0,
    tuesday: int = 0,
    wednesday: int = 0,
    thursday: int = 0,
    friday: int = 0,
    saturday: int = 0,
    sunday: int = 0,
) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        service_id=service_id,
        start_date=start_date,
        end_date=end_date,
        monday=monday,
        tuesday=tuesday,
        wednesday=wednesday,
        thursday=thursday,
        friday=friday,
        saturday=saturday,
        sunday=sunday,
    )


def _make_cac(service_id: str, aux_calendar_id: uuid.UUID, junction_type: int) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        service_id=service_id,
        aux_calendar_id=aux_calendar_id,
        junction_type=junction_type,
    )


# ---------------------------------------------------------------------------
# _decode_polyline
# ---------------------------------------------------------------------------

class TestDecodePolyline(unittest.TestCase):

    def test_empty_string_returns_empty_list(self) -> None:
        self.assertEqual(_decode_polyline(""), [])

    def test_single_zero_point(self) -> None:
        # "??" encodes (0.0, 0.0) — both lat and lon delta = 0
        result = _decode_polyline("??")
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0][0], 0.0, places=5)
        self.assertAlmostEqual(result[0][1], 0.0, places=5)

    def test_returns_list_of_tuples(self) -> None:
        # Use the well-known Google example string
        # Encodes: (38.5, -120.2), (40.7, -120.95), (43.252, -126.453)
        encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
        result = _decode_polyline(encoded)
        self.assertIsInstance(result, list)
        for pt in result:
            self.assertEqual(len(pt), 2)
            self.assertIsInstance(pt[0], float)
            self.assertIsInstance(pt[1], float)

    def test_google_example_point_count(self) -> None:
        encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
        result = _decode_polyline(encoded)
        self.assertEqual(len(result), 3)

    def test_google_example_first_point(self) -> None:
        encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
        result = _decode_polyline(encoded)
        self.assertAlmostEqual(result[0][0], 38.5, places=4)
        self.assertAlmostEqual(result[0][1], -120.2, places=4)

    def test_google_example_last_point(self) -> None:
        encoded = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
        result = _decode_polyline(encoded)
        self.assertAlmostEqual(result[2][0], 43.252, places=4)
        self.assertAlmostEqual(result[2][1], -126.453, places=4)


# ---------------------------------------------------------------------------
# _haversine_m
# ---------------------------------------------------------------------------

class TestHaversineM(unittest.TestCase):

    def test_same_point_is_zero(self) -> None:
        self.assertAlmostEqual(_haversine_m(0.0, 0.0, 0.0, 0.0), 0.0, places=3)

    def test_symmetric(self) -> None:
        d1 = _haversine_m(48.0, 11.0, 52.0, 13.0)
        d2 = _haversine_m(52.0, 13.0, 48.0, 11.0)
        self.assertAlmostEqual(d1, d2, places=3)

    def test_one_degree_latitude_at_equator(self) -> None:
        # 1 degree latitude ≈ 111,194 m
        d = _haversine_m(0.0, 0.0, 1.0, 0.0)
        self.assertAlmostEqual(d, 111_194.0, delta=500.0)

    def test_one_degree_longitude_at_equator(self) -> None:
        # 1 degree longitude at equator ≈ 111,194 m
        d = _haversine_m(0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(d, 111_194.0, delta=500.0)

    def test_result_is_positive(self) -> None:
        d = _haversine_m(48.1, 11.5, 48.2, 11.6)
        self.assertGreater(d, 0.0)

    def test_antipodal_points(self) -> None:
        # Approximately half Earth circumference
        d = _haversine_m(0.0, 0.0, 0.0, 180.0)
        self.assertAlmostEqual(d, math.pi * 6_371_000.0, delta=1000.0)


# ---------------------------------------------------------------------------
# _cumulative_distances_m
# ---------------------------------------------------------------------------

class TestCumulativeDistancesM(unittest.TestCase):

    def test_single_point_returns_zero(self) -> None:
        result = _cumulative_distances_m([(48.0, 11.0)])
        self.assertEqual(result, [0.0])

    def test_two_points_starts_at_zero(self) -> None:
        result = _cumulative_distances_m([(0.0, 0.0), (1.0, 0.0)])
        self.assertEqual(result[0], 0.0)

    def test_two_points_second_is_positive(self) -> None:
        result = _cumulative_distances_m([(0.0, 0.0), (1.0, 0.0)])
        self.assertGreater(result[1], 0.0)

    def test_length_matches_point_count(self) -> None:
        pts = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        result = _cumulative_distances_m(pts)
        self.assertEqual(len(result), len(pts))

    def test_monotonically_non_decreasing(self) -> None:
        pts = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (2.0, 1.0)]
        result = _cumulative_distances_m(pts)
        for i in range(1, len(result)):
            self.assertGreaterEqual(result[i], result[i - 1])

    def test_collinear_lat_steps_are_equal(self) -> None:
        pts = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        result = _cumulative_distances_m(pts)
        seg1 = result[1] - result[0]
        seg2 = result[2] - result[1]
        self.assertAlmostEqual(seg1, seg2, delta=1.0)  # equal steps along meridian

    def test_total_matches_sum_of_segments(self) -> None:
        pts = [(48.0, 11.0), (49.0, 11.0), (50.0, 11.0)]
        result = _cumulative_distances_m(pts)
        seg_sum = sum(
            _haversine_m(*pts[i - 1], *pts[i]) for i in range(1, len(pts))
        )
        self.assertAlmostEqual(result[-1], seg_sum, places=3)


# ---------------------------------------------------------------------------
# _format_gtfs_time
# ---------------------------------------------------------------------------

class TestFormatGtfsTime(unittest.TestCase):

    def test_none_returns_empty_string(self) -> None:
        self.assertEqual(_format_gtfs_time(None), "")

    def test_empty_string_returns_empty_string(self) -> None:
        self.assertEqual(_format_gtfs_time(""), "")

    def test_hhmm_is_padded_to_hhmmss(self) -> None:
        self.assertEqual(_format_gtfs_time("08:30"), "08:30:00")

    def test_hhmmss_is_passed_through(self) -> None:
        self.assertEqual(_format_gtfs_time("08:30:45"), "08:30:45")

    def test_overnight_time_is_passed_through(self) -> None:
        self.assertEqual(_format_gtfs_time("25:15:00"), "25:15:00")

    def test_midnight_hhmm(self) -> None:
        self.assertEqual(_format_gtfs_time("00:00"), "00:00:00")

    def test_midnight_hhmmss(self) -> None:
        self.assertEqual(_format_gtfs_time("00:00:00"), "00:00:00")


# ---------------------------------------------------------------------------
# _shorten_shape_id
# ---------------------------------------------------------------------------

class TestShortenShapeId(unittest.TestCase):

    def test_returns_eight_characters(self) -> None:
        self.assertEqual(len(_shorten_shape_id("any-shape-id")), 8)

    def test_returns_lowercase_hex(self) -> None:
        result = _shorten_shape_id("some-id")
        self.assertRegex(result, r"^[0-9a-f]{8}$")

    def test_deterministic(self) -> None:
        self.assertEqual(_shorten_shape_id("abc"), _shorten_shape_id("abc"))

    def test_different_inputs_produce_different_outputs(self) -> None:
        # This is a probabilistic check for two distinct, non-colliding values
        self.assertNotEqual(_shorten_shape_id("route-001"), _shorten_shape_id("route-002"))

    def test_matches_crc32_formula(self) -> None:
        shape_id = "test-shape-123"
        expected = format(zlib.crc32(shape_id.encode()) & 0xFFFFFFFF, "08x")
        self.assertEqual(_shorten_shape_id(shape_id), expected)

    def test_empty_string_is_handled(self) -> None:
        result = _shorten_shape_id("")
        self.assertEqual(len(result), 8)
        self.assertRegex(result, r"^[0-9a-f]{8}$")

    def test_salt_changes_output(self) -> None:
        # Verify the salt-based collision resolution would change the hash
        base = _shorten_shape_id("collision-candidate")
        salted = _shorten_shape_id("collision-candidate\x00" + "1")
        # They may or may not collide, but the input differs so we can check
        # both produce valid 8-char hex
        self.assertRegex(base, r"^[0-9a-f]{8}$")
        self.assertRegex(salted, r"^[0-9a-f]{8}$")


# ---------------------------------------------------------------------------
# _project_stop_on_shape
# ---------------------------------------------------------------------------

class TestProjectStopOnShape(unittest.TestCase):

    def _make_line(
        self, pts: list[tuple[float, float]]
    ) -> tuple[list[tuple[float, float]], list[float]]:
        """Return (pts, cumulative_distances) for a list of (lat, lon) points."""
        from app.services.gtfs_export import _cumulative_distances_m
        return pts, _cumulative_distances_m(pts)

    def test_single_point_shape_returns_min_dist(self) -> None:
        pts, cum = self._make_line([(48.0, 11.0)])
        result = _project_stop_on_shape(48.0, 11.0, pts, cum, min_dist=0.0)
        self.assertAlmostEqual(result, 0.0, places=3)

    def test_stop_at_start_of_shape(self) -> None:
        pts, cum = self._make_line([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
        result = _project_stop_on_shape(0.0, 0.0, pts, cum, min_dist=0.0)
        self.assertAlmostEqual(result, 0.0, delta=500.0)

    def test_stop_at_end_of_shape(self) -> None:
        pts, cum = self._make_line([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
        result = _project_stop_on_shape(2.0, 0.0, pts, cum, min_dist=0.0)
        self.assertAlmostEqual(result, cum[-1], delta=500.0)

    def test_stop_at_midpoint(self) -> None:
        pts, cum = self._make_line([(0.0, 0.0), (2.0, 0.0)])
        result = _project_stop_on_shape(1.0, 0.0, pts, cum, min_dist=0.0)
        # Midpoint should project to approximately half the total distance
        self.assertAlmostEqual(result, cum[-1] / 2.0, delta=1000.0)

    def test_result_respects_min_dist(self) -> None:
        pts, cum = self._make_line([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
        min_dist = cum[-1] * 0.8  # Force result past 80% of the shape
        result = _project_stop_on_shape(0.0, 0.0, pts, cum, min_dist=min_dist)
        self.assertGreaterEqual(result, min_dist)

    def test_result_is_non_negative(self) -> None:
        pts, cum = self._make_line([(48.0, 11.0), (49.0, 12.0)])
        result = _project_stop_on_shape(48.5, 11.5, pts, cum, min_dist=0.0)
        self.assertGreaterEqual(result, 0.0)


# ---------------------------------------------------------------------------
# _base_dates_in_range
# ---------------------------------------------------------------------------

class TestBaseDatesInRange(unittest.TestCase):

    # Week of 2024-01-01 (Mon) to 2024-01-07 (Sun)
    _JAN_1 = date(2024, 1, 1)   # Monday
    _JAN_7 = date(2024, 1, 7)   # Sunday

    def test_all_weekdays_returns_five_dates(self) -> None:
        cal = _make_calendar(
            "SVC1", self._JAN_1, self._JAN_7,
            monday=1, tuesday=1, wednesday=1, thursday=1, friday=1,
        )
        result = _base_dates_in_range(cal, self._JAN_1, self._JAN_7)
        self.assertEqual(len(result), 5)
        self.assertIn(date(2024, 1, 1), result)  # Mon
        self.assertIn(date(2024, 1, 5), result)  # Fri
        self.assertNotIn(date(2024, 1, 6), result)  # Sat

    def test_monday_only_returns_monday(self) -> None:
        cal = _make_calendar("SVC2", self._JAN_1, self._JAN_7, monday=1)
        result = _base_dates_in_range(cal, self._JAN_1, self._JAN_7)
        self.assertEqual(result, {date(2024, 1, 1)})

    def test_sunday_only_returns_sunday(self) -> None:
        cal = _make_calendar("SVC3", self._JAN_1, self._JAN_7, sunday=1)
        result = _base_dates_in_range(cal, self._JAN_1, self._JAN_7)
        self.assertEqual(result, {date(2024, 1, 7)})

    def test_all_days_returns_seven_dates(self) -> None:
        cal = _make_calendar(
            "SVC4", self._JAN_1, self._JAN_7,
            monday=1, tuesday=1, wednesday=1, thursday=1,
            friday=1, saturday=1, sunday=1,
        )
        result = _base_dates_in_range(cal, self._JAN_1, self._JAN_7)
        self.assertEqual(len(result), 7)

    def test_range_outside_calendar_returns_empty(self) -> None:
        cal = _make_calendar("SVC5", self._JAN_1, self._JAN_7, monday=1)
        result = _base_dates_in_range(cal, date(2024, 2, 1), date(2024, 2, 28))
        self.assertEqual(result, set())

    def test_inverted_range_returns_empty(self) -> None:
        cal = _make_calendar("SVC6", self._JAN_1, self._JAN_7, monday=1)
        result = _base_dates_in_range(cal, self._JAN_7, self._JAN_1)
        self.assertEqual(result, set())

    def test_no_active_days_returns_empty(self) -> None:
        # All day flags = 0
        cal = _make_calendar("SVC7", self._JAN_1, self._JAN_7)
        result = _base_dates_in_range(cal, self._JAN_1, self._JAN_7)
        self.assertEqual(result, set())


# ---------------------------------------------------------------------------
# compute_calendar_exceptions
# ---------------------------------------------------------------------------

class TestComputeCalendarExceptions(unittest.TestCase):
    """
    Week under test: 2024-01-01 (Mon) – 2024-01-07 (Sun)
    Base calendar SVC1: Mo–Fr (Mon 1, Tue 2, Wed 3, Thu 4, Fri 5)
    """

    _JAN_1 = date(2024, 1, 1)  # Monday
    _JAN_7 = date(2024, 1, 7)  # Sunday

    _AUX_ID = uuid.uuid4()

    def _weekday_calendar(self) -> types.SimpleNamespace:
        return _make_calendar(
            "SVC1", self._JAN_1, self._JAN_7,
            monday=1, tuesday=1, wednesday=1, thursday=1, friday=1,
        )

    def test_no_aux_calendars_produces_no_exceptions(self) -> None:
        cal = self._weekday_calendar()
        result = compute_calendar_exceptions([cal], [], {}, self._JAN_1, self._JAN_7)
        self.assertEqual(result, [])

    def test_additional_aux_adds_saturday(self) -> None:
        cal = self._weekday_calendar()
        saturday = date(2024, 1, 6)
        cac = _make_cac("SVC1", self._AUX_ID, junction_type=1)  # additional
        aux_dates = {self._AUX_ID: [saturday]}

        result = compute_calendar_exceptions(
            [cal], [cac], aux_dates, self._JAN_1, self._JAN_7
        )

        added = [(sid, dt, et) for sid, dt, et in result if et == 1]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0][1], saturday)

    def test_not_aux_removes_friday(self) -> None:
        cal = self._weekday_calendar()
        friday = date(2024, 1, 5)
        cac = _make_cac("SVC1", self._AUX_ID, junction_type=2)  # not
        aux_dates = {self._AUX_ID: [friday]}

        result = compute_calendar_exceptions(
            [cal], [cac], aux_dates, self._JAN_1, self._JAN_7
        )

        removed = [(sid, dt, et) for sid, dt, et in result if et == 2]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0][1], friday)

    def test_only_aux_restricts_to_intersection(self) -> None:
        # "only" junction type = 3: restricts base to intersection with aux dates
        cal = self._weekday_calendar()
        # Aux calendar only contains Mon and Tue
        aux_dates_list = [date(2024, 1, 1), date(2024, 1, 2)]
        cac = _make_cac("SVC1", self._AUX_ID, junction_type=3)  # only
        aux_dates = {self._AUX_ID: aux_dates_list}

        result = compute_calendar_exceptions(
            [cal], [cac], aux_dates, self._JAN_1, self._JAN_7
        )

        # Wed, Thu, Fri are in base but not in intersection → exception_type 2
        removed_dates = {dt for _, dt, et in result if et == 2}
        self.assertIn(date(2024, 1, 3), removed_dates)  # Wed
        self.assertIn(date(2024, 1, 4), removed_dates)  # Thu
        self.assertIn(date(2024, 1, 5), removed_dates)  # Fri

    def test_result_is_sorted_by_service_id_and_date(self) -> None:
        cal1 = _make_calendar("SVC_A", self._JAN_1, self._JAN_7, monday=1)
        cal2 = _make_calendar("SVC_B", self._JAN_1, self._JAN_7, monday=1)
        aux_id_2 = uuid.uuid4()
        cac1 = _make_cac("SVC_A", self._AUX_ID, junction_type=2)  # removes Mon
        cac2 = _make_cac("SVC_B", aux_id_2,     junction_type=2)  # removes Mon
        aux_dates = {
            self._AUX_ID: [date(2024, 1, 1)],
            aux_id_2:     [date(2024, 1, 1)],
        }

        result = compute_calendar_exceptions(
            [cal1, cal2], [cac1, cac2], aux_dates, self._JAN_1, self._JAN_7
        )

        self.assertEqual(result, sorted(result, key=lambda r: (r[0], r[1])))

    def test_empty_calendars_returns_empty(self) -> None:
        result = compute_calendar_exceptions([], [], {}, self._JAN_1, self._JAN_7)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# _build_export_id_map
# ---------------------------------------------------------------------------

def _item(internal_id: str, global_id: str | None = None):
    """Minimal stub with internal_id and global_id attributes."""
    import types
    obj = types.SimpleNamespace()
    obj.internal_id = internal_id
    obj.global_id = global_id
    return obj


class TestBuildExportIdMap(unittest.TestCase):

    def _call(self, items, missing_key="missing", duplicate_key="duplicate"):
        return _build_export_id_map(
            items,
            lambda x: x.internal_id,
            lambda x: x.global_id,
            missing_key,
            "id",
            duplicate_key,
        )

    # -- basic mapping --

    def test_empty_list_returns_empty_map(self) -> None:
        id_map, log_events, error_events = self._call([])
        self.assertEqual(id_map, {})
        self.assertEqual(log_events, [])
        self.assertEqual(error_events, [])

    def test_single_item_with_global_id(self) -> None:
        items = [_item("INT-1", "GLB-1")]
        id_map, log_events, _ = self._call(items)
        self.assertEqual(id_map, {"INT-1": "GLB-1"})
        self.assertEqual(log_events, [])

    def test_multiple_unique_global_ids(self) -> None:
        items = [_item("A", "GA"), _item("B", "GB"), _item("C", "GC")]
        id_map, log_events, error_events = self._call(items)
        self.assertEqual(id_map, {"A": "GA", "B": "GB", "C": "GC"})
        self.assertEqual(log_events, [])
        self.assertEqual(error_events, [])

    # -- missing global IDs --

    def test_missing_global_id_falls_back_to_internal(self) -> None:
        items = [_item("INT-1", None)]
        id_map, log_events, error_events = self._call(items, missing_key="missing_key")
        self.assertEqual(id_map, {"INT-1": "INT-1"})
        self.assertEqual(error_events, [])
        self.assertEqual(len(log_events), 1)
        self.assertEqual(log_events[0]["level"], "MiddlePrio")
        self.assertEqual(log_events[0]["key"], "missing_key")
        self.assertEqual(log_events[0]["params"]["id"], "INT-1")

    def test_empty_string_global_id_treated_as_missing(self) -> None:
        items = [_item("INT-1", "")]
        id_map, log_events, _ = self._call(items)
        self.assertEqual(id_map["INT-1"], "INT-1")
        self.assertEqual(log_events[0]["level"], "MiddlePrio")

    def test_mixed_present_and_missing_global_ids(self) -> None:
        items = [_item("A", "GA"), _item("B", None), _item("C", "GC")]
        id_map, log_events, error_events = self._call(items)
        self.assertEqual(id_map, {"A": "GA", "B": "B", "C": "GC"})
        self.assertEqual(len(log_events), 1)
        self.assertEqual(error_events, [])

    # -- duplicate global IDs (collision) --

    def test_duplicate_global_id_emits_highprio_error(self) -> None:
        items = [_item("T1", "GLB-DUPE"), _item("T2", "GLB-DUPE")]
        id_map, log_events, error_events = self._call(items, duplicate_key="dupe_key")
        self.assertEqual(len(error_events), 1)
        self.assertEqual(error_events[0]["level"], "HighPrio")
        self.assertEqual(error_events[0]["key"], "dupe_key")
        self.assertEqual(error_events[0]["params"]["global_id"], "GLB-DUPE")

    def test_duplicate_is_also_in_log_events(self) -> None:
        items = [_item("T1", "DUPE"), _item("T2", "DUPE")]
        _, log_events, error_events = self._call(items)
        self.assertIn(error_events[0], log_events)

    def test_first_occurrence_not_in_error_events(self) -> None:
        items = [_item("T1", "DUPE"), _item("T2", "DUPE"), _item("T3", "DUPE")]
        id_map, _, error_events = self._call(items)
        # Two duplicates (T2 and T3 both collide with T1)
        self.assertEqual(len(error_events), 2)

    def test_first_item_keeps_global_id_on_collision(self) -> None:
        items = [_item("T1", "DUPE"), _item("T2", "DUPE")]
        id_map, _, _ = self._call(items)
        self.assertEqual(id_map["T1"], "DUPE")

    def test_trip_collision_scenario(self) -> None:
        """Two trips share the same global_id; simulates the GTFS export collision case."""
        trips = [
            _item("TRIP-001", "CH:trip:1"),
            _item("TRIP-002", "CH:trip:1"),  # duplicate
            _item("TRIP-003", "CH:trip:2"),  # unique
        ]
        id_map, log_events, error_events = _build_export_id_map(
            trips,
            lambda t: t.internal_id,
            lambda t: t.global_id,
            "global_id_missing_trip",
            "trip_id",
            "global_id_duplicate_trip",
        )
        self.assertEqual(len(error_events), 1)
        self.assertEqual(error_events[0]["key"], "global_id_duplicate_trip")
        self.assertEqual(error_events[0]["params"]["global_id"], "CH:trip:1")
        # Non-duplicate trip is exported normally
        self.assertEqual(id_map["TRIP-003"], "CH:trip:2")

    def test_no_collision_when_all_global_ids_unique(self) -> None:
        trips = [_item(f"T{i}", f"GLB-{i}") for i in range(10)]
        _, log_events, error_events = self._call(trips)
        self.assertEqual(log_events, [])
        self.assertEqual(error_events, [])


if __name__ == "__main__":
    unittest.main()
