"""
Test configuration setup.

Sets required environment variables and adjusts sys.path before any app
modules are imported.  Import this module first in every test file:

    from tests.test_config import setup_test_environment
    setup_test_environment()
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def setup_test_environment() -> None:
    """Set minimal environment variables required by app.config.Settings."""
    defaults: dict[str, str] = {
        "SECRET_KEY":    "test-secret-key-min-32-bytes-long!!",   # >= 32 chars
        "DATABASE_URL":  "postgresql+asyncpg://test:test@localhost:5432/test",
        "DEBUG":         "true",
        "DOCS_ENABLED":  "true",
        "ALGORITHM":     "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "FIRST_SUPERUSER_PASSWORD":    "test-password",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)

    # Add backend/src to path so tests can import 'app.*' without Docker
    backend_dir = Path(__file__).parent.parent
    src_dir = backend_dir / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def configure_test_logging() -> None:
    """Suppress noisy loggers during test runs."""
    logging.getLogger("uvicorn").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


# Apply automatically on import
setup_test_environment()
configure_test_logging()
