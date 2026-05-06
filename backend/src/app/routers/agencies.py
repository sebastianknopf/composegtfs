from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, HttpUrl, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import Agency, Route, User, Version
from app.permissions import Permission, require

router = APIRouter(prefix="/api/versions/{version_id}/agencies", tags=["agencies"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AgencyOut(BaseModel):
    version_id:      uuid.UUID
    agency_id:       str
    agency_name:     str
    agency_url:      str
    agency_timezone: str
    agency_lang:     str | None
    agency_phone:    str | None
    agency_fare_url: str | None
    agency_email:    str | None
    cemv_support:    int | None

    model_config = {"from_attributes": True}


class AgencyCreate(BaseModel):
    agency_id:       str
    agency_name:     str
    agency_url:      str
    agency_timezone: str
    agency_lang:     str | None = None
    agency_phone:    str | None = None
    agency_fare_url: str | None = None
    agency_email:    str | None = None
    cemv_support:    int | None = None

    @field_validator("agency_id")
    @classmethod
    def agency_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("agency_id must not be empty")
        if len(v) > 255:
            raise ValueError("agency_id must not exceed 255 characters")
        return v

    @field_validator("agency_name")
    @classmethod
    def agency_name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("agency_name must not be empty")
        if len(v) > 255:
            raise ValueError("agency_name must not exceed 255 characters")
        return v

    @field_validator("agency_url")
    @classmethod
    def agency_url_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("agency_url must not be empty")
        if len(v) > 2048:
            raise ValueError("agency_url must not exceed 2048 characters")
        return v

    @field_validator("agency_timezone")
    @classmethod
    def agency_timezone_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("agency_timezone must not be empty")
        if len(v) > 64:
            raise ValueError("agency_timezone must not exceed 64 characters")
        return v

    @field_validator("cemv_support")
    @classmethod
    def cemv_support_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1, 2):
            raise ValueError("cemv_support must be 0, 1, or 2")
        return v


class AgencyUpdate(BaseModel):
    agency_name:     str | None = None
    agency_url:      str | None = None
    agency_timezone: str | None = None
    agency_lang:     str | None = None
    agency_phone:    str | None = None
    agency_fare_url: str | None = None
    agency_email:    str | None = None
    cemv_support:    int | None = None

    @field_validator("agency_name")
    @classmethod
    def agency_name_not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("agency_name must not be empty")
        if len(v) > 255:
            raise ValueError("agency_name must not exceed 255 characters")
        return v

    @field_validator("agency_url")
    @classmethod
    def agency_url_not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("agency_url must not be empty")
        if len(v) > 2048:
            raise ValueError("agency_url must not exceed 2048 characters")
        return v

    @field_validator("agency_timezone")
    @classmethod
    def agency_timezone_not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("agency_timezone must not be empty")
        if len(v) > 64:
            raise ValueError("agency_timezone must not exceed 64 characters")
        return v

    @field_validator("cemv_support")
    @classmethod
    def cemv_support_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1, 2):
            raise ValueError("cemv_support must be 0, 1, or 2")
        return v


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _get_version_or_404(version_id: uuid.UUID, session: AsyncSession) -> Version:
    version = await session.get(Version, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    return version


async def _get_agency_or_404(
    version_id: uuid.UUID,
    agency_id: str,
    session: AsyncSession,
) -> Agency:
    result = await session.execute(
        select(Agency).where(
            Agency.version_id == version_id,
            Agency.agency_id == agency_id,
        )
    )
    agency = result.scalar_one_or_none()
    if agency is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agency not found.")
    return agency


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=list[AgencyOut],
    summary="List all agencies for a version",
    dependencies=[require(Permission.AGENCY_READ)],
)
async def list_agencies(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Agency]:
    await _get_version_or_404(version_id, session)
    result = await session.execute(
        select(Agency)
        .where(Agency.version_id == version_id)
        .order_by(Agency.agency_id)
    )
    return list(result.scalars().all())


@router.post(
    "",
    response_model=AgencyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new agency within a version",
    dependencies=[require(Permission.AGENCY_WRITE)],
)
async def create_agency(
    version_id: uuid.UUID,
    body: AgencyCreate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Agency:
    await _get_version_or_404(version_id, session)

    existing = await session.execute(
        select(Agency).where(
            Agency.version_id == version_id,
            Agency.agency_id == body.agency_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An agency with this ID already exists in the version.",
        )

    agency = Agency(
        version_id=version_id,
        agency_id=body.agency_id,
        agency_name=body.agency_name,
        agency_url=body.agency_url,
        agency_timezone=body.agency_timezone,
        agency_lang=body.agency_lang,
        agency_phone=body.agency_phone,
        agency_fare_url=body.agency_fare_url,
        agency_email=body.agency_email,
        cemv_support=body.cemv_support,
    )
    session.add(agency)
    await session.commit()
    await session.refresh(agency)
    return agency


@router.get(
    "/{agency_id}",
    response_model=AgencyOut,
    summary="Get a single agency by ID within a version",
    dependencies=[require(Permission.AGENCY_READ)],
)
async def get_agency(
    version_id: uuid.UUID,
    agency_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Agency:
    await _get_version_or_404(version_id, session)
    return await _get_agency_or_404(version_id, agency_id, session)


@router.put(
    "/{agency_id}",
    response_model=AgencyOut,
    summary="Update an agency within a version",
    dependencies=[require(Permission.AGENCY_WRITE)],
)
async def update_agency(
    version_id: uuid.UUID,
    agency_id: str,
    body: AgencyUpdate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Agency:
    await _get_version_or_404(version_id, session)
    agency = await _get_agency_or_404(version_id, agency_id, session)

    if body.agency_name is not None:
        agency.agency_name = body.agency_name
    if body.agency_url is not None:
        agency.agency_url = body.agency_url
    if body.agency_timezone is not None:
        agency.agency_timezone = body.agency_timezone
    # Nullable fields: always apply when present in the payload
    if "agency_lang" in body.model_fields_set:
        agency.agency_lang = body.agency_lang
    if "agency_phone" in body.model_fields_set:
        agency.agency_phone = body.agency_phone
    if "agency_fare_url" in body.model_fields_set:
        agency.agency_fare_url = body.agency_fare_url
    if "agency_email" in body.model_fields_set:
        agency.agency_email = body.agency_email
    if "cemv_support" in body.model_fields_set:
        agency.cemv_support = body.cemv_support

    await session.commit()
    await session.refresh(agency)
    return agency


@router.delete(
    "/{agency_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an agency within a version",
    dependencies=[require(Permission.AGENCY_DELETE)],
)
async def delete_agency(
    version_id: uuid.UUID,
    agency_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await _get_version_or_404(version_id, session)
    agency = await _get_agency_or_404(version_id, agency_id, session)
    # Null out agency_id on routes referencing this agency before deleting.
    # The composite FK (version_id, agency_id) → agencies uses ON DELETE SET NULL,
    # but PostgreSQL cannot NULL version_id (NOT NULL). Clear it manually instead.
    await session.execute(
        select(Route)
        .where(Route.version_id == version_id, Route.agency_id == agency_id)
    )  # warm up ORM identity map
    from sqlalchemy import update as sa_update
    await session.execute(
        sa_update(Route)
        .where(Route.version_id == version_id, Route.agency_id == agency_id)
        .values(agency_id=None)
    )
    await session.delete(agency)
    await session.commit()
