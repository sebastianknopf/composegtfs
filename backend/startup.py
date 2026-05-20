#!/usr/bin/env python3
"""Startup script: run Alembic migrations, then seed the database, then start uvicorn."""
from __future__ import annotations

import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("startup")

# Ensure the backend src directory is on the path so app.* imports work
_SRC = os.path.join(os.path.dirname(__file__), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    logger.info("Running Alembic migrations …")

    # alembic.ini lives next to this file (in backend/)
    _ini = os.path.join(os.path.dirname(__file__), "alembic.ini")
    alembic_cfg = Config(_ini)

    # Override the URL so we never rely on the placeholder in alembic.ini
    db_url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")
    logger.info("Migrations complete.")


async def run_seed() -> None:
    from composegtfs.database import AsyncSessionLocal
    from composegtfs.seed import seed_initial_data, seed_initial_version

    logger.info("Seeding database …")
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)
        await seed_initial_version(session)
    logger.info("Seeding complete.")


def start_server() -> None:
    import uvicorn
    from composegtfs.config import settings

    logger.info("Starting uvicorn on %s:%d …", settings.host, settings.port)
    uvicorn.run(
        "composegtfs.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    run_migrations()
    asyncio.run(run_seed())
    start_server()
