---
description: "Backend development instructions for Python/FastAPI service. Use when: modifying Python code, API endpoints, database models, migrations, adapters, backend services, or backend tests."
applyTo:
  - "backend/**/*.py"
  - "backend/pyproject.toml"
  - "backend/Dockerfile"
---

# Backend Development Instructions

## Project Structure

- The backend uses a **src-layout**: application source code lives under `backend/src/`, not directly in `backend/`
- The package is declared in `backend/pyproject.toml` with `[tool.setuptools.packages.find] where = ["src"]` (or equivalent for the build backend in use)
- Tests live in `backend/tests/` (outside `src/`) and import from the installed or editable package
- Alembic migration files live in `backend/alembic/`

## Python Version Compatibility

- **Target Python version**: >= 3.10
- All code must remain compatible with Python 3.10 and newer versions
- Do not use Python features that require versions newer than 3.10 unless explicitly approved

## Dependency Management

- **Explicit approval required** before adding new packages to `pyproject.toml`
- Dependencies are declared in `pyproject.toml` under `[project.dependencies]`
- When suggesting new dependencies, explicitly ask for approval and explain why the dependency is needed
- Prefer using existing dependencies when possible

## Testing Requirements

### Test Framework
- **Use only `unittest` module** from Python standard library
- Do not import pytest, nose, or other testing frameworks without explicit approval

### Test Execution
- All tests must be discoverable and runnable with: `python -m unittest discover`
- Tests are located in `backend/tests/` directory
- Test files must follow the pattern `test_*.py`
- Test classes must inherit from `unittest.TestCase`

### Test Coverage
- **New modules** must include corresponding unit tests
- **New functions and methods** should be covered by tests
- Tests should verify both success and error cases
- Use descriptive test method names

### Modifying Existing Tests
- **Critical**: Only modify unit tests when the expected output of the tested method changes
- When refactoring code without changing behavior:
  - **Do NOT modify the tests** – they verify the contract remains intact
  - **Only modify the implementation** being tested
- Modify tests only when:
  - The method's public API changes (parameters, return type)
  - The expected behavior or output changes
  - Fixing a bug that the test should have caught

### Test Structure Example
```python
import unittest
from app.module import function_to_test

class TestModuleName(unittest.TestCase):
    def setUp(self) -> None:
        pass

    def tearDown(self) -> None:
        pass

    def test_function_success_case(self) -> None:
        result = function_to_test(valid_input)
        self.assertEqual(result, expected_output)

    def test_function_error_case(self) -> None:
        with self.assertRaises(ExpectedException):
            function_to_test(invalid_input)
```

## Code Style

### Language Requirements
- **All code must be written in English**
  - Variable names, function names, class names in English
  - Comments and docstrings in English
  - Error messages and log messages in English
- Non-English languages are **only allowed** for user-facing text via the frontend localization system

### Conventions
- **Strict type hints are mandatory** on all function signatures (parameters and return types), class attributes, and variables where the type is not immediately obvious
- Use `from __future__ import annotations` at the top of files where needed for forward references
- Use async/await for all database operations (SQLAlchemy async)
- Follow PEP 8 style guidelines
- Use meaningful variable and function names
- Keep functions focused and single-purpose

### Imports
- Group imports: standard library, third-party, local imports
- Use absolute imports from the `app` package
- Avoid wildcard imports (`from module import *`)

### Error Handling
- Use appropriate exception types
- Log errors using the configured logger
- Provide meaningful error messages
- Handle database errors gracefully

## Database Migrations (Alembic)

### General Rules
- **All schema changes must be managed via Alembic migrations** – never modify the database schema directly
- Migration scripts live in `alembic/versions/`
- The `alembic.ini` and `alembic/env.py` must be kept in sync with the SQLAlchemy models

### Creating Migrations
- Auto-generate migrations from model changes: `alembic revision --autogenerate -m "<description>"`
- **Always review auto-generated migrations** before applying – autogenerate can miss or misinterpret changes (e.g., renamed columns, custom types, constraints)
- Use a short, descriptive slug in the revision message (e.g., `add_user_email_index`, `drop_legacy_tokens_table`)

### Migration Conventions
- One logical change per migration file – do not bundle unrelated schema changes
- Provide both `upgrade()` and `downgrade()` implementations unless a downgrade is genuinely not possible; in that case, raise `NotImplementedError` with an explanation
- Never delete or edit a migration that has already been applied to any environment
- Use `server_default` instead of `default` for database-level defaults in column definitions
- Prefer `nullable=False` with a `server_default` over allowing nulls when adding columns to existing tables

### Naming Conventions
- Constraint names must be explicit and follow this pattern:
  - Primary keys: `pk_<table>`
  - Foreign keys: `fk_<table>_<column>_<referenced_table>`
  - Unique constraints: `uq_<table>_<column>`
  - Indexes: `ix_<table>_<column>`
- Use `naming_convention` in the SQLAlchemy `MetaData` to enforce this automatically:

```python
from sqlalchemy import MetaData

metadata = MetaData(naming_convention={
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
})
```

### Running Migrations
- Apply pending migrations: `alembic upgrade head`
- Rollback one step: `alembic downgrade -1`
- Show current revision: `alembic current`
- Show migration history: `alembic history --verbose`

## API Development

### FastAPI Routers
- Each router handles a specific domain
- Use Pydantic models for request/response validation
- Routers are thin: they handle HTTP concerns only (input parsing, response shaping, status codes)
- **Business logic must not live inside routers** – extract it into dedicated service modules

### Service Layer
- Shared logic (e.g., database access, business rules, external calls) belongs in service modules, not in routers
- A service is a plain Python module or class with typed functions – no FastAPI dependencies
- Multiple routers may depend on the same service; never duplicate logic across routers
- Services receive dependencies (e.g., DB sessions) via parameters, not by importing global state

### Response Models
- Define clear Pydantic schemas with strict type hints for all endpoints
- Use proper HTTP status codes
- Return meaningful error messages

### Authentication

- **Endpoints are protected by default.** Every endpoint requires a valid authenticated session unless explicitly declared public.
- Public endpoints must be marked clearly, e.g. by applying a dedicated `public` dependency or by documenting the intent with a comment.
- Authentication is enforced via a FastAPI dependency (e.g., `Depends(get_current_user)`) injected at the router or endpoint level.
- The dependency resolves the current user from the request (e.g., via a JWT bearer token or session cookie) and raises `HTTP 401` if the credential is missing or invalid.
- Endpoints that require specific roles or permissions raise `HTTP 403` when the authenticated user lacks the required access.
- **Never rely on obscurity** – omitting auth from an endpoint must be a conscious, documented decision.

### Token Lifecycle

- JWTs must carry an `exp` claim. Tokens without an expiry are not permitted.
- Use a **sliding expiry** pattern: on every authenticated request, if the token is still valid but within a configurable renewal window (e.g., the remaining lifetime is less than half the total TTL), issue a fresh token with a new `exp` and return it to the client (e.g., via a response header or response body field).
- The total token TTL and the renewal threshold must be configurable via environment variables – never hard-coded.
- The client is responsible for storing the refreshed token and using it for subsequent requests.
- Expired tokens must be rejected with `HTTP 401`; the client must then redirect to the login flow.

## Security

- Never commit secrets or credentials
- Use environment variables for configuration

## Common Patterns

### Logging
```python
import logging

logger = logging.getLogger(__name__)
logger.info("Information message")
logger.error("Error message", exc_info=True)
```

## Before Committing

- Run tests: `python -m unittest discover`
- Ensure compatibility with Python >= 3.10
- Verify no new dependencies were added without approval
- Verify all migration files have both `upgrade()` and `downgrade()` implemented
