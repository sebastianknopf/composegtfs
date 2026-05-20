"""Unit tests for app.services.generate_global_ids."""
from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from composegtfs.services.generate_global_ids import GlobalIdResolutionError, GlobalIdResult, _resolve, generate_global_ids


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trip(trip_id: str, *, service_id: str | None = None,
          short_name: str | None = None, global_id: str | None = None) -> SimpleNamespace:
    t = SimpleNamespace()
    t.trip_id = trip_id
    t.route_id = "R1"
    t.service_id = service_id
    t.trip_short_name = short_name
    t.global_id = global_id
    return t


def _route(route_id: str = "R1", *, agency_id: str | None = "A1",
           global_id: str | None = None) -> SimpleNamespace:
    r = SimpleNamespace()
    r.route_id = route_id
    r.agency_id = agency_id
    r.global_id = global_id
    return r


def _agency(agency_id: str = "A1", *, global_id: str | None = None) -> SimpleNamespace:
    a = SimpleNamespace()
    a.agency_id = agency_id
    a.global_id = global_id
    return a


def _make_session(trip, route=None, agency=None):
    """Build a minimal AsyncMock session that returns the given objects.

    The service executes queries in this order:
      1. SELECT Trip  → scalars().all()
      2. SELECT Route → scalar_one_or_none()
      3. SELECT Agency (only when route.agency_id is truthy) → scalar_one_or_none()
    """
    responses: list = []

    trips_mock = MagicMock()
    trips_mock.scalars.return_value.all.return_value = [trip] if trip is not None else []
    responses.append(trips_mock)

    route_mock = MagicMock()
    route_mock.scalar_one_or_none.return_value = route
    responses.append(route_mock)

    if route is not None and (route.agency_id or ""):
        agency_mock = MagicMock()
        agency_mock.scalar_one_or_none.return_value = agency
        responses.append(agency_mock)

    # Use a mutable index so the inner function can mutate it
    idx = [0]

    async def _execute(_query):
        result = responses[idx[0]]
        idx[0] += 1
        return result

    session = AsyncMock()
    session.execute = _execute
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Tests for _resolve (pure function)
# ---------------------------------------------------------------------------

class TestResolve(unittest.TestCase):

    def _call(self, preset: str, **kwargs) -> str:
        defaults = dict(
            agency_id="", agency_global_id="",
            line_id="", line_global_id="",
            day_type_id="", trip_short_name="",
            trip_id="T1",
        )
        defaults.update(kwargs)
        return _resolve(preset, **defaults)

    def test_static_string(self):
        self.assertEqual(self._call("STATIC"), "STATIC")

    def test_agency_id(self):
        self.assertEqual(self._call("{AgencyId}", agency_id="AGENCY1"), "AGENCY1")

    def test_agency_global_id(self):
        self.assertEqual(self._call("{AgencyGlobalId}", agency_global_id="GA1"), "GA1")

    def test_line_id(self):
        self.assertEqual(self._call("{LineId}", line_id="LINE1"), "LINE1")

    def test_line_global_id(self):
        self.assertEqual(self._call("{LineGlobalId}", line_global_id="GLINE"), "GLINE")

    def test_day_type_id(self):
        self.assertEqual(self._call("{DayTypeId}", day_type_id="WD"), "WD")

    def test_trip_short_name(self):
        self.assertEqual(self._call("{TripShortName}", trip_short_name="99"), "99")

    def test_uuid_is_deterministic(self):
        r1 = self._call("{UUID}", trip_id="TRIP-42")
        r2 = self._call("{UUID}", trip_id="TRIP-42")
        self.assertEqual(r1, r2)
        uuid.UUID(r1)  # must parse as a valid UUID

    def test_uuid_differs_per_trip(self):
        r1 = self._call("{UUID}", trip_id="T1")
        r2 = self._call("{UUID}", trip_id="T2")
        self.assertNotEqual(r1, r2)

    def test_generated_number_is_six_digits(self):
        r = self._call("{GeneratedNumber}")
        self.assertEqual(len(r), 6)
        self.assertTrue(r.isdigit())

    def test_combined_preset(self):
        result = self._call(
            "{AgencyId}/{LineId}/{DayTypeId}",
            agency_id="A1", line_id="R1", day_type_id="MO",
        )
        self.assertEqual(result, "A1/R1/MO")

    def test_unknown_placeholder_preserved(self):
        result = self._call("{Unknown}", trip_id="T1")
        self.assertEqual(result, "{Unknown}")


# ---------------------------------------------------------------------------
# Tests for generate_global_ids (async)
# ---------------------------------------------------------------------------

class TestGenerateGlobalIds(unittest.IsolatedAsyncioTestCase):

    async def test_empty_trip_ids_returns_zeros(self):
        session = AsyncMock()
        result = await generate_global_ids(
            version_id=uuid.uuid4(), route_id="R1", trip_ids=[],
            preset="{LineId}", overwrite=False, session=session,
        )
        self.assertEqual(result, GlobalIdResult(updated=0, skipped=0))
        session.execute.assert_not_called()

    async def test_no_matching_trips_returns_skipped(self):
        # Session returns empty trips list
        trips_mock = MagicMock()
        trips_mock.scalars.return_value.all.return_value = []
        session = AsyncMock()
        session.execute = AsyncMock(return_value=trips_mock)

        result = await generate_global_ids(
            version_id=uuid.uuid4(), route_id="R1", trip_ids=["T1", "T2"],
            preset="{LineId}", overwrite=False, session=session,
        )
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.skipped, 2)

    async def test_skip_when_global_id_exists_and_no_overwrite(self):
        t = _trip("T1", global_id="EXISTING")
        session = _make_session(t, _route(), _agency())

        result = await generate_global_ids(
            version_id=uuid.uuid4(), route_id="R1", trip_ids=["T1"],
            preset="{LineId}", overwrite=False, session=session,
        )
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(t.global_id, "EXISTING")
        session.commit.assert_not_called()

    async def test_overwrite_replaces_existing_global_id(self):
        t = _trip("T1", global_id="OLD")
        session = _make_session(t, _route(route_id="LINE7"), _agency())

        result = await generate_global_ids(
            version_id=uuid.uuid4(), route_id="R1", trip_ids=["T1"],
            preset="{LineId}", overwrite=True, session=session,
        )
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(t.global_id, "LINE7")
        session.commit.assert_called_once()

    async def test_set_new_global_id(self):
        t = _trip("T1", service_id="WD", global_id=None)
        session = _make_session(t, _route(route_id="R1"), _agency(agency_id="A1"))

        result = await generate_global_ids(
            version_id=uuid.uuid4(), route_id="R1", trip_ids=["T1"],
            preset="{AgencyId}/{LineId}/{DayTypeId}", overwrite=False, session=session,
        )
        self.assertEqual(result.updated, 1)
        self.assertEqual(t.global_id, "A1/R1/WD")

    async def test_uuid_placeholder_is_deterministic(self):
        trip_id = "TRIP-UUID-TEST"
        t1 = _trip(trip_id, global_id=None)
        t2 = _trip(trip_id, global_id=None)
        vid = uuid.uuid4()

        session1 = _make_session(t1, _route(), _agency())
        await generate_global_ids(
            version_id=vid, route_id="R1", trip_ids=[trip_id],
            preset="{UUID}", overwrite=False, session=session1,
        )

        session2 = _make_session(t2, _route(), _agency())
        await generate_global_ids(
            version_id=vid, route_id="R1", trip_ids=[trip_id],
            preset="{UUID}", overwrite=False, session=session2,
        )

        self.assertEqual(t1.global_id, t2.global_id)
        uuid.UUID(t1.global_id)  # must be a valid UUID string

    async def test_no_agency_when_route_has_no_agency_id(self):
        t = _trip("T1", global_id=None)
        session = _make_session(t, _route(agency_id=None), agency=None)

        with self.assertRaises(GlobalIdResolutionError):
            await generate_global_ids(
                version_id=uuid.uuid4(), route_id="R1", trip_ids=["T1"],
                preset="{AgencyId}", overwrite=False, session=session,
            )

    async def test_agency_global_id_missing_raises(self):
        t = _trip("T1", global_id=None)
        session = _make_session(t, _route(agency_id="A1"), _agency(agency_id="A1", global_id=None))

        with self.assertRaises(GlobalIdResolutionError):
            await generate_global_ids(
                version_id=uuid.uuid4(), route_id="R1", trip_ids=["T1"],
                preset="{AgencyGlobalId}", overwrite=False, session=session,
            )

    async def test_line_global_id_missing_raises(self):
        t = _trip("T1", global_id=None)
        session = _make_session(t, _route(route_id="R1", global_id=None), _agency())

        with self.assertRaises(GlobalIdResolutionError):
            await generate_global_ids(
                version_id=uuid.uuid4(), route_id="R1", trip_ids=["T1"],
                preset="{LineGlobalId}", overwrite=False, session=session,
            )

    async def test_day_type_id_missing_raises(self):
        t = _trip("T1", service_id=None, global_id=None)
        session = _make_session(t, _route(), _agency())

        with self.assertRaises(GlobalIdResolutionError):
            await generate_global_ids(
                version_id=uuid.uuid4(), route_id="R1", trip_ids=["T1"],
                preset="{DayTypeId}", overwrite=False, session=session,
            )

    async def test_trip_short_name_missing_raises(self):
        t = _trip("T1", short_name=None, global_id=None)
        session = _make_session(t, _route(), _agency())

        with self.assertRaises(GlobalIdResolutionError):
            await generate_global_ids(
                version_id=uuid.uuid4(), route_id="R1", trip_ids=["T1"],
                preset="{TripShortName}", overwrite=False, session=session,
            )

    async def test_validation_only_for_trips_to_update(self):
        """Skipped trips (already have global_id, overwrite=False) are not validated."""
        t = _trip("T1", service_id=None, global_id="ALREADY_SET")
        session = _make_session(t, _route(), _agency())

        # Would fail validation if T1 were in trips_to_update, but it's skipped
        result = await generate_global_ids(
            version_id=uuid.uuid4(), route_id="R1", trip_ids=["T1"],
            preset="{DayTypeId}", overwrite=False, session=session,
        )
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.skipped, 1)


if __name__ == "__main__":
    unittest.main()
