"""
Unit tests for app.permissions — permission registry and enum consistency.
"""

from __future__ import annotations

import unittest

# Must be first: sets env vars and adjusts sys.path
import tests.test_config  # noqa: F401

from app.permissions import (
    ALL_CODENAMES,
    PERMISSION_GROUPS,
    Permission,
    PermissionDef,
    PermissionGroup,
)


class TestPermissionRegistry(unittest.TestCase):
    """Tests for PERMISSION_GROUPS and ALL_CODENAMES."""

    def test_permission_groups_is_non_empty(self) -> None:
        self.assertGreater(len(PERMISSION_GROUPS), 0)

    def test_all_groups_have_unique_keys(self) -> None:
        keys = [g.key for g in PERMISSION_GROUPS]
        self.assertEqual(len(keys), len(set(keys)), "Duplicate group keys found")

    def test_all_groups_have_permissions(self) -> None:
        for group in PERMISSION_GROUPS:
            with self.subTest(group=group.key):
                self.assertGreater(len(group.permissions), 0)

    def test_all_codenames_is_non_empty(self) -> None:
        self.assertGreater(len(ALL_CODENAMES), 0)

    def test_all_codenames_contains_every_group_permission(self) -> None:
        for group in PERMISSION_GROUPS:
            for perm in group.permissions:
                with self.subTest(codename=perm.codename):
                    self.assertIn(perm.codename, ALL_CODENAMES)

    def test_no_duplicate_codenames_in_groups(self) -> None:
        all_codes = [
            p.codename
            for g in PERMISSION_GROUPS
            for p in g.permissions
        ]
        self.assertEqual(
            len(all_codes),
            len(set(all_codes)),
            f"Duplicate codenames: {[c for c in all_codes if all_codes.count(c) > 1]}",
        )

    def test_all_codenames_count_matches_flat_list(self) -> None:
        flat_count = sum(len(g.permissions) for g in PERMISSION_GROUPS)
        self.assertEqual(len(ALL_CODENAMES), flat_count)

    def test_codenames_follow_resource_action_pattern(self) -> None:
        for codename in ALL_CODENAMES:
            with self.subTest(codename=codename):
                parts = codename.split(":")
                self.assertEqual(len(parts), 2, f"Expected 'resource:action', got '{codename}'")
                resource, action = parts
                self.assertTrue(resource, "Resource part must not be empty")
                self.assertTrue(action, "Action part must not be empty")

    def test_group_lang_keys_are_non_empty(self) -> None:
        for group in PERMISSION_GROUPS:
            with self.subTest(group=group.key):
                self.assertTrue(group.lang_key)

    def test_permission_lang_keys_are_non_empty(self) -> None:
        for group in PERMISSION_GROUPS:
            for perm in group.permissions:
                with self.subTest(codename=perm.codename):
                    self.assertTrue(perm.lang_key)

    def test_known_groups_are_present(self) -> None:
        keys = {g.key for g in PERMISSION_GROUPS}
        for expected in ("accounts", "groups", "versions", "network", "schedule", "gtfs"):
            with self.subTest(key=expected):
                self.assertIn(expected, keys)


class TestPermissionEnum(unittest.TestCase):
    """Tests for the Permission enum and its alignment with ALL_CODENAMES."""

    def test_permission_enum_is_non_empty(self) -> None:
        self.assertGreater(len(Permission), 0)

    def test_every_enum_value_is_in_all_codenames(self) -> None:
        for member in Permission:
            with self.subTest(member=member.name):
                self.assertIn(member.value, ALL_CODENAMES)

    def test_every_codename_has_enum_member(self) -> None:
        enum_values = {m.value for m in Permission}
        for codename in ALL_CODENAMES:
            with self.subTest(codename=codename):
                self.assertIn(codename, enum_values)

    def test_enum_and_registry_are_in_sync(self) -> None:
        """The set of enum values and ALL_CODENAMES must be identical."""
        enum_values = frozenset(m.value for m in Permission)
        self.assertEqual(enum_values, ALL_CODENAMES)

    def test_permission_enum_members_are_strings(self) -> None:
        for member in Permission:
            with self.subTest(member=member.name):
                self.assertIsInstance(member.value, str)

    def test_known_permissions_exist(self) -> None:
        known = [
            Permission.ACCOUNTS_READ,
            Permission.VERSIONS_WRITE,
            Permission.SCHEDULE_DELETE,
            Permission.GTFS_EXPORT,
        ]
        for perm in known:
            with self.subTest(perm=perm):
                self.assertIn(perm.value, ALL_CODENAMES)


class TestPermissionDataClasses(unittest.TestCase):
    """Tests for PermissionDef and PermissionGroup data structures."""

    def test_permission_def_is_frozen(self) -> None:
        pdef = PermissionDef(codename="test:read", lang_key="test.read")
        with self.assertRaises((AttributeError, TypeError)):
            pdef.codename = "changed"  # type: ignore[misc]

    def test_permission_group_is_frozen(self) -> None:
        pgroup = PermissionGroup(key="test", lang_key="test.group", permissions=[])
        with self.assertRaises((AttributeError, TypeError)):
            pgroup.key = "changed"  # type: ignore[misc]

    def test_permission_def_equality(self) -> None:
        p1 = PermissionDef(codename="res:act", lang_key="res.act")
        p2 = PermissionDef(codename="res:act", lang_key="res.act")
        self.assertEqual(p1, p2)

    def test_permission_group_equality(self) -> None:
        perms = [PermissionDef(codename="res:read", lang_key="res.read")]
        g1 = PermissionGroup(key="res", lang_key="res.group", permissions=perms)
        g2 = PermissionGroup(key="res", lang_key="res.group", permissions=perms)
        self.assertEqual(g1, g2)


if __name__ == "__main__":
    unittest.main()
