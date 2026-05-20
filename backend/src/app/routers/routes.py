from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models import Agency, Route, User, Version
from app.permissions import Permission, require

router = APIRouter(prefix="/api/versions/{version_id}/routes", tags=["routes"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RouteOut(BaseModel):
    version_id:          uuid.UUID
    route_id:            str
    agency_id:           str | None
    route_short_name:    str | None
    route_long_name:     str | None
    route_desc:          str | None
    route_type:          int
    route_url:           str | None
    route_color:         str | None
    route_text_color:    str | None
    route_sort_order:    int | None
    continuous_pickup:   int | None
    continuous_drop_off: int | None
    network_id:          str | None
    cemv_support:        int | None
    global_id:           str | None

    model_config = {"from_attributes": True}


class RouteCreate(BaseModel):
    route_id:            str
    agency_id:           str | None = None
    route_short_name:    str | None = None
    route_long_name:     str | None = None
    route_desc:          str | None = None
    route_type:          int
    route_url:           str | None = None
    route_color:         str | None = None
    route_text_color:    str | None = None
    route_sort_order:    int | None = None
    continuous_pickup:   int | None = None
    continuous_drop_off: int | None = None
    network_id:          str | None = None
    cemv_support:        int | None = None
    global_id:           str | None = None

    @field_validator("route_id")
    @classmethod
    def route_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("route_id must not be empty")
        if len(v) > 255:
            raise ValueError("route_id must not exceed 255 characters")
        return v

    @field_validator("route_type")
    @classmethod
    def route_type_valid(cls, v: int) -> int:
        if v not in (0, 1, 2, 3, 4, 5, 6, 7, 11, 12):
            raise ValueError("route_type must be a valid GTFS route type (0-7, 11, 12)")
        return v

    @field_validator("route_color", "route_text_color")
    @classmethod
    def hex_color_valid(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) != 6 or not all(c in "0123456789ABCDEFabcdef" for c in v):
            raise ValueError("Color must be a 6-character hexadecimal string (without #)")
        return v.upper()

    @field_validator("continuous_pickup", "continuous_drop_off")
    @classmethod
    def continuous_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1, 2, 3):
            raise ValueError("Value must be 0, 1, 2, or 3")
        return v

    @field_validator("route_sort_order")
    @classmethod
    def sort_order_non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("route_sort_order must be a non-negative integer")
        return v

    @field_validator("cemv_support")
    @classmethod
    def cemv_support_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1, 2):
            raise ValueError("cemv_support must be 0, 1, or 2")
        return v

    @model_validator(mode="after")
    def short_or_long_name_required(self) -> RouteCreate:
        short = (self.route_short_name or "").strip()
        long_ = (self.route_long_name or "").strip()
        if not short and not long_:
            raise ValueError(
                "At least one of route_short_name or route_long_name must be provided."
            )
        return self


class RouteUpdate(BaseModel):
    agency_id:           str | None = None
    route_short_name:    str | None = None
    route_long_name:     str | None = None
    route_desc:          str | None = None
    route_type:          int | None = None
    route_url:           str | None = None
    route_color:         str | None = None
    route_text_color:    str | None = None
    route_sort_order:    int | None = None
    continuous_pickup:   int | None = None
    continuous_drop_off: int | None = None
    network_id:          str | None = None
    cemv_support:        int | None = None
    global_id:           str | None = None

    @field_validator("route_type")
    @classmethod
    def route_type_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1, 2, 3, 4, 5, 6, 7, 11, 12):
            raise ValueError("route_type must be a valid GTFS route type (0-7, 11, 12)")
        return v

    @field_validator("route_color", "route_text_color")
    @classmethod
    def hex_color_valid(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) != 6 or not all(c in "0123456789ABCDEFabcdef" for c in v):
            raise ValueError("Color must be a 6-character hexadecimal string (without #)")
        return v.upper()

    @field_validator("continuous_pickup", "continuous_drop_off")
    @classmethod
    def continuous_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1, 2, 3):
            raise ValueError("Value must be 0, 1, 2, or 3")
        return v

    @field_validator("route_sort_order")
    @classmethod
    def sort_order_non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("route_sort_order must be a non-negative integer")
        return v

    @field_validator("cemv_support")
    @classmethod
    def cemv_support_valid(cls, v: int | None) -> int | None:
        if v is not None and v not in (0, 1, 2):
            raise ValueError("cemv_support must be 0, 1, or 2")
        return v


class AgencyRef(BaseModel):
    agency_id:   str
    agency_name: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_version_or_404(version_id: uuid.UUID, session: AsyncSession) -> Version:
    version = await session.get(Version, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    return version


async def _get_route_or_404(
    version_id: uuid.UUID,
    route_id: str,
    session: AsyncSession,
) -> Route:
    result = await session.execute(
        select(Route).where(
            Route.version_id == version_id,
            Route.route_id == route_id,
        )
    )
    route = result.scalar_one_or_none()
    if route is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found.")
    return route


async def _check_agency_exists(
    version_id: uuid.UUID,
    agency_id: str,
    session: AsyncSession,
) -> None:
    result = await session.execute(
        select(Agency).where(
            Agency.version_id == version_id,
            Agency.agency_id == agency_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agency not found in this version.",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=list[RouteOut],
    summary="List all routes for a version",
    dependencies=[require(Permission.ROUTES_READ)],
)
async def list_routes(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Route]:
    await _get_version_or_404(version_id, session)
    result = await session.execute(
        select(Route)
        .where(Route.version_id == version_id)
        .order_by(Route.route_sort_order.nullslast(), Route.route_id)
    )
    return list(result.scalars().all())


@router.post(
    "",
    response_model=RouteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new route within a version",
    dependencies=[require(Permission.ROUTES_WRITE)],
)
async def create_route(
    version_id: uuid.UUID,
    body: RouteCreate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Route:
    await _get_version_or_404(version_id, session)

    if body.agency_id is not None:
        await _check_agency_exists(version_id, body.agency_id, session)

    existing = await session.execute(
        select(Route).where(
            Route.version_id == version_id,
            Route.route_id == body.route_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A route with this ID already exists in the version.",
        )

    route = Route(
        version_id=version_id,
        route_id=body.route_id,
        agency_id=body.agency_id,
        route_short_name=body.route_short_name,
        route_long_name=body.route_long_name,
        route_desc=body.route_desc,
        route_type=body.route_type,
        route_url=body.route_url,
        route_color=body.route_color,
        route_text_color=body.route_text_color,
        route_sort_order=body.route_sort_order,
        continuous_pickup=body.continuous_pickup,
        continuous_drop_off=body.continuous_drop_off,
        network_id=body.network_id,
        cemv_support=body.cemv_support,
        global_id=body.global_id,
    )
    session.add(route)
    await session.commit()
    await session.refresh(route)
    return route


@router.get(
    "/agencies",
    response_model=list[AgencyRef],
    summary="List agencies available for assignment within a version (requires routes:read)",
    dependencies=[require(Permission.ROUTES_READ)],
)
async def list_agencies_for_routes(
    version_id: uuid.UUID,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Agency]:
    await _get_version_or_404(version_id, session)
    result = await session.execute(
        select(Agency)
        .where(Agency.version_id == version_id)
        .order_by(Agency.agency_name)
    )
    return list(result.scalars().all())


@router.get(
    "/{route_id}",
    response_model=RouteOut,
    summary="Get a single route by ID within a version",
    dependencies=[require(Permission.ROUTES_READ)],
)
async def get_route(
    version_id: uuid.UUID,
    route_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Route:
    await _get_version_or_404(version_id, session)
    return await _get_route_or_404(version_id, route_id, session)


@router.put(
    "/{route_id}",
    response_model=RouteOut,
    summary="Update a route within a version",
    dependencies=[require(Permission.ROUTES_WRITE)],
)
async def update_route(
    version_id: uuid.UUID,
    route_id: str,
    body: RouteUpdate,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Route:
    await _get_version_or_404(version_id, session)
    route = await _get_route_or_404(version_id, route_id, session)

    # agency_id supports explicit null to clear the assignment
    if 'agency_id' in body.model_fields_set:
        if body.agency_id is not None:
            await _check_agency_exists(version_id, body.agency_id, session)
        route.agency_id = body.agency_id

    # route_short_name and route_type must not be nulled (required fields)
    if body.route_short_name is not None:
        route.route_short_name = body.route_short_name
    if body.route_type is not None:
        route.route_type = body.route_type

    # All other fields support explicit null to clear the value
    _NULLABLE_ROUTE_FIELDS = (
        "route_long_name", "route_desc", "route_url",
        "route_color", "route_text_color", "route_sort_order",
        "continuous_pickup", "continuous_drop_off", "network_id", "cemv_support",
        "global_id",
    )
    for field in _NULLABLE_ROUTE_FIELDS:
        if field in body.model_fields_set:
            setattr(route, field, getattr(body, field))

    await session.commit()
    await session.refresh(route)
    return route


@router.delete(
    "/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a route within a version",
    dependencies=[require(Permission.ROUTES_DELETE)],
)
async def delete_route(
    version_id: uuid.UUID,
    route_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await _get_version_or_404(version_id, session)
    route = await _get_route_or_404(version_id, route_id, session)
    await session.delete(route)
    await session.commit()
