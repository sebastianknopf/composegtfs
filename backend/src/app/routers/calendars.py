from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import AuxCalendar, AuxCalendarDate, Calendar, CalendarAuxCalendar, User, Version
from app.permissions import Permission, require

# Two sub-routers sharing the same permission set, mounted in main.py
calendars_router = APIRouter(
    prefix="/api/versions/{version_id}/calendars",
    tags=["calendars"],
)
aux_calendars_router = APIRouter(
    prefix="/api/versions/{version_id}/aux-calendars",
    tags=["aux-calendars"],
)


# ---------------------------------------------------------------------------
# Schemas — Calendars (Tagesarten)
# ---------------------------------------------------------------------------

class CalendarOut(BaseModel):
    version_id: uuid.UUID
    service_id: str
    name:      str | None
    monday:    int
    tuesday:   int
    wednesday: int
    thursday:  int
    friday:    int
    saturday:  int
    sunday:    int
    start_date: date
    end_date:   date

    model_config = {"from_attributes": True}


class CalendarCreate(BaseModel):
    service_id: str
    name:      str | None = None
    monday:    int
    tuesday:   int
    wednesday: int
    thursday:  int
    friday:    int
    saturday:  int
    sunday:    int
    start_date: date
    end_date:   date

    @field_validator("service_id")
    @classmethod
    def service_id_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("service_id must not be empty")
        if len(v) > 255:
            raise ValueError("service_id must not exceed 255 characters")
        return v

    @field_validator("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    @classmethod
    def day_flag_valid(cls, v: int) -> int:
        if v not in (0, 1):
            raise ValueError("Day flags must be 0 or 1")
        return v

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start is not None and v < start:
            raise ValueError("end_date must not be before start_date")
        return v


class CalendarUpdate(BaseModel):
    name:      str | None = None
    monday:    int | None = None
    tuesday:   int | None = None
    wednesday: int | None = None
    thursday:  int | None = None
    friday:    int | None = None
    saturday:  int | None = None
    sunday:    int | None = None
    start_date: date | None = None
    end_date:   date | None = None

    @field_validator("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    @classmethod
    def day_flag_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1):
            raise ValueError("Day flags must be 0 or 1")
        return v


# ---------------------------------------------------------------------------
# Schemas — AuxCalendars (Hilfskalender)
# ---------------------------------------------------------------------------

class AuxCalendarOut(BaseModel):
    id:         uuid.UUID
    version_id: uuid.UUID
    name:       str

    model_config = {"from_attributes": True}


class AuxCalendarCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        if len(v) > 255:
            raise ValueError("name must not exceed 255 characters")
        return v


class AuxCalendarUpdate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        if len(v) > 255:
            raise ValueError("name must not exceed 255 characters")
        return v


# ---------------------------------------------------------------------------
# Schemas — AuxCalendarDates
# ---------------------------------------------------------------------------

class AuxCalendarDateOut(BaseModel):
    aux_calendar_id: uuid.UUID
    date: date

    model_config = {"from_attributes": True}


class AuxCalendarDatesAdd(BaseModel):
    dates: list[date]

    @field_validator("dates")
    @classmethod
    def dates_not_empty(cls, v: list[date]) -> list[date]:
        if not v:
            raise ValueError("dates must not be empty")
        return list(set(v))  # deduplicate


# ---------------------------------------------------------------------------
# Schemas — CalendarAuxCalendar junction
# ---------------------------------------------------------------------------

class CalendarAuxCalendarOut(BaseModel):
    version_id:      uuid.UUID
    service_id:      str
    aux_calendar_id: uuid.UUID
    junction_type:   int

    model_config = {"from_attributes": True}


class CalendarAuxCalendarCreate(BaseModel):
    aux_calendar_id: uuid.UUID
    junction_type:   int

    @field_validator("junction_type")
    @classmethod
    def junction_type_valid(cls, v: int) -> int:
        if v not in (1, 2, 3):
            raise ValueError("junction_type must be 1 (additional), 2 (not) or 3 (only/restrict)")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_version_or_404(version_id: uuid.UUID, session: AsyncSession) -> Version:
    version = await session.get(Version, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    return version


async def _get_calendar_or_404(
    version_id: uuid.UUID,
    service_id: str,
    session: AsyncSession,
) -> Calendar:
    result = await session.execute(
        select(Calendar).where(
            Calendar.version_id == version_id,
            Calendar.service_id == service_id,
        )
    )
    calendar = result.scalar_one_or_none()
    if calendar is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar not found.")
    return calendar


async def _get_aux_calendar_or_404(
    version_id: uuid.UUID,
    aux_calendar_id: uuid.UUID,
    session: AsyncSession,
) -> AuxCalendar:
    result = await session.execute(
        select(AuxCalendar).where(
            AuxCalendar.id == aux_calendar_id,
            AuxCalendar.version_id == version_id,
        )
    )
    aux_cal = result.scalar_one_or_none()
    if aux_cal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aux calendar not found.")
    return aux_cal


# ---------------------------------------------------------------------------
# Endpoints — Calendars (Tagesarten)
# ---------------------------------------------------------------------------

@calendars_router.get(
    "",
    response_model=list[CalendarOut],
    summary="List all calendars (Tagesarten) for a version",
    dependencies=[require(Permission.CALENDAR_READ)],
)
async def list_calendars(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Calendar]:
    await _get_version_or_404(version_id, session)
    result = await session.execute(
        select(Calendar)
        .where(Calendar.version_id == version_id)
        .order_by(Calendar.service_id)
    )
    return list(result.scalars().all())


@calendars_router.get(
    "/max-date",
    response_model=dict,
    summary="Return the maximum end_date across all calendars for a version",
    dependencies=[require(Permission.GTFS_EXPORT)],
)
async def get_calendars_max_date(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _get_version_or_404(version_id, session)
    result = await session.execute(
        select(func.max(Calendar.end_date)).where(Calendar.version_id == version_id)
    )
    max_date: date | None = result.scalar_one_or_none()
    return {"max_date": max_date.isoformat() if max_date else None}


@calendars_router.post(
    "",
    response_model=CalendarOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a calendar (Tagesart)",
    dependencies=[require(Permission.CALENDAR_WRITE)],
)
async def create_calendar(
    version_id: uuid.UUID,
    body: CalendarCreate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Calendar:
    await _get_version_or_404(version_id, session)
    existing = await session.execute(
        select(Calendar).where(
            Calendar.version_id == version_id,
            Calendar.service_id == body.service_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A calendar with this service_id already exists in this version.",
        )
    calendar = Calendar(version_id=version_id, **body.model_dump())
    session.add(calendar)
    await session.commit()
    await session.refresh(calendar)
    return calendar


@calendars_router.get(
    "/{service_id}",
    response_model=CalendarOut,
    summary="Get a single calendar (Tagesart)",
    dependencies=[require(Permission.CALENDAR_READ)],
)
async def get_calendar(
    version_id: uuid.UUID,
    service_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Calendar:
    return await _get_calendar_or_404(version_id, service_id, session)


@calendars_router.put(
    "/{service_id}",
    response_model=CalendarOut,
    summary="Update a calendar (Tagesart)",
    dependencies=[require(Permission.CALENDAR_WRITE)],
)
async def update_calendar(
    version_id: uuid.UUID,
    service_id: str,
    body: CalendarUpdate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Calendar:
    calendar = await _get_calendar_or_404(version_id, service_id, session)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(calendar, field, value)
    # Validate start/end ordering after partial update
    if calendar.end_date < calendar.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must not be before start_date.",
        )
    await session.commit()
    await session.refresh(calendar)
    return calendar


@calendars_router.delete(
    "/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a calendar (Tagesart)",
    dependencies=[require(Permission.CALENDAR_DELETE)],
)
async def delete_calendar(
    version_id: uuid.UUID,
    service_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    calendar = await _get_calendar_or_404(version_id, service_id, session)
    await session.delete(calendar)
    await session.commit()


# ---------------------------------------------------------------------------
# Endpoints — CalendarAuxCalendar assignments (under calendar resource)
# ---------------------------------------------------------------------------

@calendars_router.get(
    "/{service_id}/aux-calendars",
    response_model=list[CalendarAuxCalendarOut],
    summary="List aux-calendar assignments for a calendar (Tagesart)",
    dependencies=[require(Permission.CALENDAR_READ)],
)
async def list_calendar_aux_calendars(
    version_id: uuid.UUID,
    service_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CalendarAuxCalendar]:
    await _get_calendar_or_404(version_id, service_id, session)
    result = await session.execute(
        select(CalendarAuxCalendar).where(
            CalendarAuxCalendar.version_id == version_id,
            CalendarAuxCalendar.service_id == service_id,
        )
    )
    return list(result.scalars().all())


@calendars_router.post(
    "/{service_id}/aux-calendars",
    response_model=CalendarAuxCalendarOut,
    status_code=status.HTTP_201_CREATED,
    summary="Assign an aux-calendar to a calendar (Tagesart)",
    dependencies=[require(Permission.CALENDAR_WRITE)],
)
async def assign_aux_calendar(
    version_id: uuid.UUID,
    service_id: str,
    body: CalendarAuxCalendarCreate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CalendarAuxCalendar:
    await _get_calendar_or_404(version_id, service_id, session)
    await _get_aux_calendar_or_404(version_id, body.aux_calendar_id, session)
    existing = await session.get(
        CalendarAuxCalendar,
        (version_id, service_id, body.aux_calendar_id),
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This aux-calendar is already assigned to this calendar.",
        )
    assignment = CalendarAuxCalendar(
        version_id=version_id,
        service_id=service_id,
        aux_calendar_id=body.aux_calendar_id,
        junction_type=body.junction_type,
    )
    session.add(assignment)
    await session.commit()
    await session.refresh(assignment)
    return assignment


@calendars_router.delete(
    "/{service_id}/aux-calendars/{aux_calendar_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an aux-calendar assignment from a calendar (Tagesart)",
    dependencies=[require(Permission.CALENDAR_DELETE)],
)
async def remove_aux_calendar_assignment(
    version_id: uuid.UUID,
    service_id: str,
    aux_calendar_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    assignment = await session.get(
        CalendarAuxCalendar,
        (version_id, service_id, aux_calendar_id),
    )
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found.",
        )
    await session.delete(assignment)
    await session.commit()


# ---------------------------------------------------------------------------
# Endpoints — AuxCalendars (Hilfskalender)
# ---------------------------------------------------------------------------

@aux_calendars_router.get(
    "",
    response_model=list[AuxCalendarOut],
    summary="List all aux-calendars (Hilfskalender) for a version",
    dependencies=[require(Permission.CALENDAR_READ)],
)
async def list_aux_calendars(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AuxCalendar]:
    await _get_version_or_404(version_id, session)
    result = await session.execute(
        select(AuxCalendar)
        .where(AuxCalendar.version_id == version_id)
        .order_by(AuxCalendar.name)
    )
    return list(result.scalars().all())


@aux_calendars_router.post(
    "",
    response_model=AuxCalendarOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an aux-calendar (Hilfskalender)",
    dependencies=[require(Permission.CALENDAR_WRITE)],
)
async def create_aux_calendar(
    version_id: uuid.UUID,
    body: AuxCalendarCreate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AuxCalendar:
    await _get_version_or_404(version_id, session)
    existing = await session.execute(
        select(AuxCalendar).where(
            AuxCalendar.version_id == version_id,
            AuxCalendar.name == body.name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An aux-calendar with this name already exists in this version.",
        )
    aux_cal = AuxCalendar(version_id=version_id, **body.model_dump())
    session.add(aux_cal)
    await session.commit()
    await session.refresh(aux_cal)
    return aux_cal


@aux_calendars_router.get(
    "/{aux_calendar_id}",
    response_model=AuxCalendarOut,
    summary="Get a single aux-calendar (Hilfskalender)",
    dependencies=[require(Permission.CALENDAR_READ)],
)
async def get_aux_calendar(
    version_id: uuid.UUID,
    aux_calendar_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AuxCalendar:
    return await _get_aux_calendar_or_404(version_id, aux_calendar_id, session)


@aux_calendars_router.put(
    "/{aux_calendar_id}",
    response_model=AuxCalendarOut,
    summary="Rename an aux-calendar (Hilfskalender)",
    dependencies=[require(Permission.CALENDAR_WRITE)],
)
async def update_aux_calendar(
    version_id: uuid.UUID,
    aux_calendar_id: uuid.UUID,
    body: AuxCalendarUpdate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AuxCalendar:
    aux_cal = await _get_aux_calendar_or_404(version_id, aux_calendar_id, session)
    conflict = await session.execute(
        select(AuxCalendar).where(
            AuxCalendar.version_id == version_id,
            AuxCalendar.name == body.name,
            AuxCalendar.id != aux_calendar_id,
        )
    )
    if conflict.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An aux-calendar with this name already exists in this version.",
        )
    aux_cal.name = body.name
    await session.commit()
    await session.refresh(aux_cal)
    return aux_cal


@aux_calendars_router.delete(
    "/{aux_calendar_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an aux-calendar (Hilfskalender) — cascades dates and assignments",
    dependencies=[require(Permission.CALENDAR_DELETE)],
)
async def delete_aux_calendar(
    version_id: uuid.UUID,
    aux_calendar_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    aux_cal = await _get_aux_calendar_or_404(version_id, aux_calendar_id, session)
    await session.delete(aux_cal)
    await session.commit()


# ---------------------------------------------------------------------------
# Endpoints — AuxCalendarDates (dates of a Hilfskalender)
# ---------------------------------------------------------------------------

@aux_calendars_router.get(
    "/{aux_calendar_id}/dates",
    response_model=list[AuxCalendarDateOut],
    summary="List all dates for an aux-calendar",
    dependencies=[require(Permission.CALENDAR_READ)],
)
async def list_aux_calendar_dates(
    version_id: uuid.UUID,
    aux_calendar_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AuxCalendarDate]:
    await _get_aux_calendar_or_404(version_id, aux_calendar_id, session)
    result = await session.execute(
        select(AuxCalendarDate)
        .where(AuxCalendarDate.aux_calendar_id == aux_calendar_id)
        .order_by(AuxCalendarDate.date)
    )
    return list(result.scalars().all())


@aux_calendars_router.post(
    "/{aux_calendar_id}/dates",
    response_model=list[AuxCalendarDateOut],
    status_code=status.HTTP_201_CREATED,
    summary="Add dates to an aux-calendar (duplicates are silently ignored)",
    dependencies=[require(Permission.CALENDAR_WRITE)],
)
async def add_aux_calendar_dates(
    version_id: uuid.UUID,
    aux_calendar_id: uuid.UUID,
    body: AuxCalendarDatesAdd,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AuxCalendarDate]:
    await _get_aux_calendar_or_404(version_id, aux_calendar_id, session)
    # Fetch existing dates to avoid duplicates
    existing_result = await session.execute(
        select(AuxCalendarDate.date).where(AuxCalendarDate.aux_calendar_id == aux_calendar_id)
    )
    existing_dates = {row[0] for row in existing_result.all()}
    new_entries = [
        AuxCalendarDate(aux_calendar_id=aux_calendar_id, date=d)
        for d in body.dates
        if d not in existing_dates
    ]
    session.add_all(new_entries)
    await session.commit()
    result = await session.execute(
        select(AuxCalendarDate)
        .where(AuxCalendarDate.aux_calendar_id == aux_calendar_id)
        .order_by(AuxCalendarDate.date)
    )
    return list(result.scalars().all())


@aux_calendars_router.delete(
    "/{aux_calendar_id}/dates/{date}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a single date from an aux-calendar",
    dependencies=[require(Permission.CALENDAR_DELETE)],
)
async def delete_aux_calendar_date(
    version_id: uuid.UUID,
    aux_calendar_id: uuid.UUID,
    date: date,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await _get_aux_calendar_or_404(version_id, aux_calendar_id, session)
    entry = await session.get(AuxCalendarDate, (aux_calendar_id, date))
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Date not found in this aux-calendar.",
        )
    await session.delete(entry)
    await session.commit()
