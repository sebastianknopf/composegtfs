"""Unit tests for app.services.version_copy.

All tests use an AsyncMock session so no real database is needed.
The tests focus on the observable contract of run_copy:

* The first yielded event is always {"status": "running"}.
* A name conflict on new-version creation yields {"status": "error", "message": "name_conflict"}.
* A missing target version yields {"status": "error", "message": "target_not_found"}.
* An exception during the copy triggers a rollback and yields an error event.
* A successful copy/merge yields {"status": "done", "version": {...}} and calls commit.
"""

import tests.test_config  # noqa: F401 — must be first; sets env vars

import types
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models import Version
from app.services.version_copy import run_copy


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _collect(gen):
    """Drain an async generator into a plain list."""
    events = []
    async for e in gen:
        events.append(e)
    return events


_ALL_FALSE = dict(
    include_agencies=False,
    include_day_types=False,
    include_stops=False,
    include_shapes=False,
    include_routes=False,
    include_route_bands=False,
    include_schedule=False,
    include_headsigns=False,
)


# ---------------------------------------------------------------------------
# New-version path  (target_version_id=None)
# ---------------------------------------------------------------------------

class TestRunCopyNewVersion(unittest.IsolatedAsyncioTestCase):
    """Tests for run_copy when creating a brand-new target version."""

    def _make_session(self, *, name_conflict: bool = False) -> AsyncMock:
        session = AsyncMock()
        scalar_mock = MagicMock()
        # scalar_one_or_none returns a truthy object when there is a conflict
        scalar_mock.scalar_one_or_none.return_value = object() if name_conflict else None
        session.execute = AsyncMock(return_value=scalar_mock)
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.refresh = AsyncMock()
        return session

    def _kwargs(self, **overrides):
        kw = dict(
            source_version_id=uuid.uuid4(),
            new_name="New Version",
            target_version_id=None,
            **_ALL_FALSE,
        )
        kw.update(overrides)
        return kw

    async def test_first_event_is_running(self):
        session = self._make_session(name_conflict=True)
        events = await _collect(run_copy(**self._kwargs(), session=session))
        self.assertEqual(events[0], {"status": "running"})

    async def test_name_conflict_yields_error_event(self):
        session = self._make_session(name_conflict=True)
        events = await _collect(run_copy(**self._kwargs(), session=session))
        self.assertEqual(events[-1], {"status": "error", "message": "name_conflict"})

    async def test_name_conflict_yields_exactly_two_events(self):
        session = self._make_session(name_conflict=True)
        events = await _collect(run_copy(**self._kwargs(), session=session))
        self.assertEqual(len(events), 2)

    def _make_session_flush_ok(self) -> tuple[AsyncMock, list]:
        """Return a session where flush sets Version.id/created_at, and a list of added objects."""
        session = self._make_session()
        added_objects: list = []
        session.add.side_effect = added_objects.append

        async def _flush():
            for obj in added_objects:
                if isinstance(obj, Version):
                    obj.id = uuid.uuid4()
                    obj.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
                    obj.sort_order = 0
                    break

        session.flush.side_effect = _flush
        return session, added_objects

    async def test_exception_during_copy_yields_error_event(self):
        # flush() is called *before* the try block in run_copy, so we trigger
        # the exception via commit.side_effect (which is inside the try block).
        session, _ = self._make_session_flush_ok()
        session.commit.side_effect = RuntimeError("commit error")
        events = await _collect(run_copy(**self._kwargs(), session=session))
        error_events = [e for e in events if e.get("status") == "error"]
        self.assertTrue(error_events)
        self.assertIn("commit error", error_events[0]["message"])

    async def test_exception_during_copy_triggers_rollback(self):
        session, _ = self._make_session_flush_ok()
        session.commit.side_effect = RuntimeError("commit error")
        await _collect(run_copy(**self._kwargs(), session=session))
        session.rollback.assert_called_once()

    async def test_successful_copy_yields_done(self):
        session, _ = self._make_session_flush_ok()
        events = await _collect(run_copy(**self._kwargs(), session=session))
        done = next((e for e in events if e.get("status") == "done"), None)
        self.assertIsNotNone(done)

    async def test_done_event_contains_version_keys(self):
        session, _ = self._make_session_flush_ok()
        events = await _collect(run_copy(**self._kwargs(), session=session))
        done = next(e for e in events if e.get("status") == "done")
        self.assertIn("version", done)
        for key in ("id", "name", "created_at", "sort_order"):
            self.assertIn(key, done["version"])

    async def test_done_event_version_name_matches_input(self):
        session, _ = self._make_session_flush_ok()
        events = await _collect(run_copy(**self._kwargs(new_name="My Copy"), session=session))
        done = next(e for e in events if e.get("status") == "done")
        self.assertEqual(done["version"]["name"], "My Copy")

    async def test_successful_copy_calls_commit_once(self):
        session, _ = self._make_session_flush_ok()
        await _collect(run_copy(**self._kwargs(), session=session))
        session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Merge-into-existing-version path  (target_version_id provided)
# ---------------------------------------------------------------------------

class TestRunCopyMergeVersion(unittest.IsolatedAsyncioTestCase):
    """Tests for run_copy when merging into an existing target version."""

    def _make_target(self) -> tuple[uuid.UUID, types.SimpleNamespace]:
        tid = uuid.uuid4()
        target = types.SimpleNamespace(
            id=tid,
            name="Existing Version",
            created_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
            sort_order=2,
        )
        return tid, target

    def _kwargs(self, target_id: uuid.UUID, **overrides):
        kw = dict(
            source_version_id=uuid.uuid4(),
            new_name=None,
            target_version_id=target_id,
            **_ALL_FALSE,
        )
        kw.update(overrides)
        return kw

    async def test_first_event_is_running(self):
        tid, _ = self._make_target()
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)  # target not found is fine here
        events = await _collect(run_copy(**self._kwargs(tid), session=session))
        self.assertEqual(events[0], {"status": "running"})

    async def test_target_not_found_yields_error(self):
        tid, _ = self._make_target()
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        events = await _collect(run_copy(**self._kwargs(tid), session=session))
        self.assertEqual(events[-1], {"status": "error", "message": "target_not_found"})

    async def test_target_not_found_yields_exactly_two_events(self):
        tid, _ = self._make_target()
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        events = await _collect(run_copy(**self._kwargs(tid), session=session))
        self.assertEqual(len(events), 2)

    async def test_exception_during_merge_yields_error(self):
        tid, target = self._make_target()
        session = AsyncMock()
        session.get = AsyncMock(return_value=target)
        session.commit = AsyncMock(side_effect=RuntimeError("commit error"))
        session.rollback = AsyncMock()
        events = await _collect(run_copy(**self._kwargs(tid), session=session))
        error_events = [e for e in events if e.get("status") == "error"]
        self.assertTrue(error_events)

    async def test_exception_during_merge_triggers_rollback(self):
        tid, target = self._make_target()
        session = AsyncMock()
        session.get = AsyncMock(return_value=target)
        session.commit = AsyncMock(side_effect=RuntimeError("commit error"))
        session.rollback = AsyncMock()
        await _collect(run_copy(**self._kwargs(tid), session=session))
        session.rollback.assert_called_once()

    async def test_successful_merge_yields_done(self):
        tid, target = self._make_target()
        session = AsyncMock()
        session.get = AsyncMock(return_value=target)
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        events = await _collect(run_copy(**self._kwargs(tid), session=session))
        done = next((e for e in events if e.get("status") == "done"), None)
        self.assertIsNotNone(done)

    async def test_successful_merge_done_contains_target_id(self):
        tid, target = self._make_target()
        session = AsyncMock()
        session.get = AsyncMock(return_value=target)
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        events = await _collect(run_copy(**self._kwargs(tid), session=session))
        done = next(e for e in events if e.get("status") == "done")
        self.assertEqual(done["version"]["id"], str(tid))

    async def test_successful_merge_calls_commit_once(self):
        tid, target = self._make_target()
        session = AsyncMock()
        session.get = AsyncMock(return_value=target)
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        await _collect(run_copy(**self._kwargs(tid), session=session))
        session.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
