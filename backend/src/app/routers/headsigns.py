from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import Headsign, User, Version
from app.permissions import Permission, require

router = APIRouter(prefix="/api/versions/{version_id}/headsigns", tags=["headsigns"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class HeadsignOut(BaseModel):
    id:          uuid.UUID
    version_id:  uuid.UUID
    name:        str
    number:      int | None
    destination: str

    model_config = {"from_attributes": True}


class HeadsignCreate(BaseModel):
    name:        str
    number:      int | None = None
    destination: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        if len(v) > 255:
            raise ValueError("name must not exceed 255 characters")
        return v

    @field_validator("number")
    @classmethod
    def number_non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("number must be non-negative")
        return v

    @field_validator("destination")
    @classmethod
    def destination_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("destination must not be empty")
        if len(v) > 255:
            raise ValueError("destination must not exceed 255 characters")
        return v


class HeadsignUpdate(BaseModel):
    name:        str | None = None
    number:      int | None = None
    destination: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        if len(v) > 255:
            raise ValueError("name must not exceed 255 characters")
        return v

    @field_validator("number")
    @classmethod
    def number_non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("number must be non-negative")
        return v

    @field_validator("destination")
    @classmethod
    def destination_not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("destination must not be empty")
        if len(v) > 255:
            raise ValueError("destination must not exceed 255 characters")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_version_or_404(version_id: uuid.UUID, session: AsyncSession) -> Version:
    version = await session.get(Version, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    return version


async def _get_headsign_or_404(
    version_id: uuid.UUID,
    headsign_id: uuid.UUID,
    session: AsyncSession,
) -> Headsign:
    result = await session.execute(
        select(Headsign).where(
            Headsign.version_id == version_id,
            Headsign.id == headsign_id,
        )
    )
    headsign = result.scalar_one_or_none()
    if headsign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Headsign not found.")
    return headsign


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=list[HeadsignOut],
    summary="List all headsigns for a version",
    dependencies=[require(Permission.HEADSIGNS_READ)],
)
async def list_headsigns(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Headsign]:
    await _get_version_or_404(version_id, session)
    result = await session.execute(
        select(Headsign)
        .where(Headsign.version_id == version_id)
        .order_by(Headsign.name)
    )
    return list(result.scalars().all())


@router.post(
    "",
    response_model=HeadsignOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new headsign",
    dependencies=[require(Permission.HEADSIGNS_WRITE)],
)
async def create_headsign(
    version_id: uuid.UUID,
    body: HeadsignCreate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Headsign:
    await _get_version_or_404(version_id, session)

    existing = await session.execute(
        select(Headsign).where(
            Headsign.version_id == version_id,
            Headsign.name == body.name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A headsign with this name already exists in this version.",
        )

    headsign = Headsign(
        version_id=version_id,
        name=body.name,
        number=body.number,
        destination=body.destination,
    )
    session.add(headsign)
    await session.commit()
    await session.refresh(headsign)
    return headsign


@router.get(
    "/{headsign_id}",
    response_model=HeadsignOut,
    summary="Get a single headsign",
    dependencies=[require(Permission.HEADSIGNS_READ)],
)
async def get_headsign(
    version_id: uuid.UUID,
    headsign_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Headsign:
    return await _get_headsign_or_404(version_id, headsign_id, session)


@router.patch(
    "/{headsign_id}",
    response_model=HeadsignOut,
    summary="Update a headsign",
    dependencies=[require(Permission.HEADSIGNS_WRITE)],
)
async def update_headsign(
    version_id: uuid.UUID,
    headsign_id: uuid.UUID,
    body: HeadsignUpdate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Headsign:
    headsign = await _get_headsign_or_404(version_id, headsign_id, session)

    if body.name is not None and body.name != headsign.name:
        existing = await session.execute(
            select(Headsign).where(
                Headsign.version_id == version_id,
                Headsign.name == body.name,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A headsign with this name already exists in this version.",
            )
        headsign.name = body.name

    if body.number is not None:
        headsign.number = body.number
    if body.destination is not None:
        headsign.destination = body.destination

    await session.commit()
    await session.refresh(headsign)
    return headsign


@router.delete(
    "/{headsign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a headsign",
    dependencies=[require(Permission.HEADSIGNS_DELETE)],
)
async def delete_headsign(
    version_id: uuid.UUID,
    headsign_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    headsign = await _get_headsign_or_404(version_id, headsign_id, session)
    await session.delete(headsign)
    await session.commit()
