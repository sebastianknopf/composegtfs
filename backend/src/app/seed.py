from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.config import settings
from app.models import User, Version

logger = logging.getLogger(__name__)


async def seed_initial_data(session: AsyncSession) -> None:
    """Create the first superuser if no users exist yet."""
    result = await session.execute(select(User).limit(1))
    if result.scalar_one_or_none() is not None:
        return  # already seeded

    username = settings.first_superuser
    email = settings.first_superuser_email
    password = settings.first_superuser_password

    if not password:
        logger.warning(
            "FIRST_SUPERUSER_PASSWORD is not set — skipping initial superuser creation. "
            "Set FIRST_SUPERUSER_PASSWORD in your .env file and restart."
        )
        return

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        is_active=True,
        is_superuser=True,
    )
    session.add(user)
    await session.commit()
    logger.info("Initial superuser '%s' created.", username)


async def seed_initial_version(session: AsyncSession) -> None:
    """Create the default version 'Version #1' if no versions exist yet."""
    result = await session.execute(select(Version).limit(1))
    if result.scalar_one_or_none() is not None:
        return  # at least one version already exists

    version = Version(name="Version #1")
    session.add(version)
    await session.commit()
    logger.info("Initial version 'Version #1' created.")
