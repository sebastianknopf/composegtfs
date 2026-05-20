"""
Unit tests for app.auth — password hashing and JWT helpers.
"""

from __future__ import annotations

import unittest
from datetime import timedelta

# Must be first: sets env vars and adjusts sys.path
import tests.test_config  # noqa: F401

import jwt

from app.auth import (
    _decode_token,
    create_access_token,
    hash_password,
    verify_password,
)
from app.config import settings


class TestPasswordHashing(unittest.TestCase):
    """Tests for hash_password and verify_password."""

    def test_hash_returns_string(self) -> None:
        hashed = hash_password("test_password")
        self.assertIsInstance(hashed, str)

    def test_hash_is_not_plain_password(self) -> None:
        plain = "my_secret"
        self.assertNotEqual(hash_password(plain), plain)

    def test_hash_length_is_sufficient(self) -> None:
        # bcrypt hashes are ~60 characters
        hashed = hash_password("any_password")
        self.assertGreater(len(hashed), 50)

    def test_same_password_produces_different_hashes(self) -> None:
        # bcrypt uses a random salt per call
        pw = "same_password"
        self.assertNotEqual(hash_password(pw), hash_password(pw))

    def test_verify_correct_password(self) -> None:
        plain = "correct_password"
        hashed = hash_password(plain)
        self.assertTrue(verify_password(plain, hashed))

    def test_verify_wrong_password(self) -> None:
        hashed = hash_password("correct_password")
        self.assertFalse(verify_password("wrong_password", hashed))

    def test_verify_empty_string_fails(self) -> None:
        hashed = hash_password("non_empty")
        self.assertFalse(verify_password("", hashed))

    def test_verify_is_case_sensitive(self) -> None:
        hashed = hash_password("MyPassword")
        self.assertFalse(verify_password("mypassword", hashed))
        self.assertFalse(verify_password("MYPASSWORD", hashed))
        self.assertTrue(verify_password("MyPassword", hashed))

    def test_verify_special_characters(self) -> None:
        plain = "P@$$w0rd!#%&*()_+-=[]{}|;:,.<>?"
        self.assertTrue(verify_password(plain, hash_password(plain)))

    def test_verify_unicode_password(self) -> None:
        plain = "пароль密码🔒"
        self.assertTrue(verify_password(plain, hash_password(plain)))


class TestCreateAccessToken(unittest.TestCase):
    """Tests for create_access_token."""

    def test_returns_string(self) -> None:
        token = create_access_token("user1")
        self.assertIsInstance(token, str)

    def test_token_has_three_parts(self) -> None:
        token = create_access_token("user1")
        self.assertEqual(len(token.split(".")), 3)

    def test_token_contains_correct_subject(self) -> None:
        token = create_access_token("alice")
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        self.assertEqual(payload["sub"], "alice")

    def test_token_contains_expiration(self) -> None:
        token = create_access_token("alice")
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        self.assertIn("exp", payload)

    def test_different_subjects_produce_different_tokens(self) -> None:
        t1 = create_access_token("user_a")
        t2 = create_access_token("user_b")
        self.assertNotEqual(t1, t2)

    def test_token_with_empty_subject(self) -> None:
        token = create_access_token("")
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        self.assertEqual(payload["sub"], "")

    def test_token_with_email_subject(self) -> None:
        token = create_access_token("user@example.com")
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        self.assertEqual(payload["sub"], "user@example.com")


class TestDecodeToken(unittest.TestCase):
    """Tests for _decode_token."""

    def test_valid_token_returns_subject(self) -> None:
        token = create_access_token("bob")
        subject = _decode_token(token)
        self.assertEqual(subject, "bob")

    def test_invalid_token_raises_http_exception(self) -> None:
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            _decode_token("not.a.token")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_token_signed_with_wrong_key_raises_http_exception(self) -> None:
        from fastapi import HTTPException
        bad_token = jwt.encode({"sub": "eve"}, "wrong-secret-key", algorithm="HS256")
        with self.assertRaises(HTTPException) as ctx:
            _decode_token(bad_token)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_expired_token_raises_http_exception(self) -> None:
        from fastapi import HTTPException
        from datetime import datetime, timezone
        expired_payload = {
            "sub": "carol",
            "exp": datetime(2000, 1, 1, tzinfo=timezone.utc),
        }
        expired_token = jwt.encode(expired_payload, settings.secret_key, algorithm=settings.algorithm)
        with self.assertRaises(HTTPException) as ctx:
            _decode_token(expired_token)
        self.assertEqual(ctx.exception.status_code, 401)


class TestSecurityIntegration(unittest.TestCase):
    """End-to-end security workflow tests."""

    def test_register_and_login_workflow(self) -> None:
        """Simulate password registration and login verification."""
        plain = "secure_user_password"
        stored_hash = hash_password(plain)

        self.assertTrue(verify_password(plain, stored_hash))
        self.assertFalse(verify_password("wrong_password", stored_hash))

    def test_create_and_decode_token_workflow(self) -> None:
        """Simulate token creation after successful authentication."""
        username = "authenticated_user"
        password = "secure_password"
        stored_hash = hash_password(password)

        self.assertTrue(verify_password(password, stored_hash))
        token = create_access_token(username)
        self.assertEqual(_decode_token(token), username)


if __name__ == "__main__":
    unittest.main()
