from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import AppSetting, User
from app.permissions import Permission, require

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Known setting keys with their default values
DEFAULTS: dict[str, str] = {
    "app.title": "composegtfs",
    "map.tile_url": "https://tiles.openfreemap.org/styles/positron",
}


class AppSettingsResponse(BaseModel):
    app_title: str
    map_tile_url: str


class AppSettingsUpdate(BaseModel):
    app_title: str
    map_tile_url: str


async def _load(session: AsyncSession) -> dict[str, str]:
    """Return all settings from DB, substituting defaults for missing rows."""
    result = await session.execute(select(AppSetting))
    stored = {row.key: row.value for row in result.scalars().all()}
    return {key: stored.get(key, default) for key, default in DEFAULTS.items()}


@router.get("", response_model=AppSettingsResponse, summary="Get application settings")
async def get_settings(
    session: AsyncSession = Depends(get_session),
) -> AppSettingsResponse:
    data = await _load(session)
    return AppSettingsResponse(
        app_title=data["app.title"],
        map_tile_url=data["map.tile_url"],
    )


@router.put("", response_model=AppSettingsResponse, summary="Save application settings")
async def save_settings(
    body: AppSettingsUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(get_current_user),
    __: None = require(Permission.SETTINGS_WRITE),
) -> AppSettingsResponse:
    updates: dict[str, str] = {
        "app.title": body.app_title,
        "map.tile_url": body.map_tile_url,
    }
    for key, value in updates.items():
        stmt = pg_insert(AppSetting).values(key=key, value=value)
        stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"value": value})
        await session.execute(stmt)
    await session.commit()
    return AppSettingsResponse(
        app_title=updates["app.title"],
        map_tile_url=updates["map.tile_url"],
    )
