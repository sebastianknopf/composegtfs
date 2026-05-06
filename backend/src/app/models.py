from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, ForeignKeyConstraint, Integer, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Association table: users <-> groups  (n:m)
# ---------------------------------------------------------------------------

class UserGroup(Base):
    __tablename__ = "user_groups"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    group_id = Column(UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)


# ---------------------------------------------------------------------------
# Group permissions  (group → permission codename, n:m via text)
# ---------------------------------------------------------------------------

class GroupPermission(Base):
    __tablename__ = "group_permissions"

    group_id   = Column(UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    permission = Column(String(64), nullable=False, primary_key=True)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(254), unique=True, nullable=False, index=True)
    hashed_password = Column(String(256), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    is_superuser = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    groups = relationship("Group", secondary="user_groups", back_populates="users", lazy="selectin")


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

class Group(Base):
    __tablename__ = "groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(64), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    users = relationship("User", secondary="user_groups", back_populates="groups", lazy="selectin")


# ---------------------------------------------------------------------------
# App Settings  (key/value store, one row per setting)
# ---------------------------------------------------------------------------

class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Versions  — top-level container for all transit data objects
# ---------------------------------------------------------------------------

class Version(Base):
    __tablename__ = "versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(128), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    agencies = relationship("Agency", back_populates="version", cascade="all, delete-orphan")
    calendars = relationship("Calendar", back_populates="version", cascade="all, delete-orphan")
    aux_calendars = relationship("AuxCalendar", back_populates="version", cascade="all, delete-orphan")
    stops = relationship("Stop", back_populates="version", cascade="all, delete-orphan")
    routes = relationship("Route", back_populates="version", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Agencies  — GTFS agency.txt entities, scoped to a Version
# ---------------------------------------------------------------------------

class Agency(Base):
    __tablename__ = "agencies"

    version_id      = Column(UUID(as_uuid=True), ForeignKey("versions.id", ondelete="CASCADE"), primary_key=True)
    agency_id       = Column(String(255), primary_key=True)

    agency_name     = Column(String(255), nullable=False)
    agency_url      = Column(String(2048), nullable=False)
    agency_timezone = Column(String(64), nullable=False)
    agency_lang     = Column(String(35), nullable=True)
    agency_phone    = Column(String(64), nullable=True)
    agency_fare_url = Column(String(2048), nullable=True)
    agency_email    = Column(String(254), nullable=True)
    cemv_support    = Column(Integer, nullable=True)

    version = relationship("Version", back_populates="agencies")


# ---------------------------------------------------------------------------
# Calendars  — GTFS calendar.txt entities, scoped to a Version
# ---------------------------------------------------------------------------

class Calendar(Base):
    __tablename__ = "calendars"

    version_id = Column(UUID(as_uuid=True), ForeignKey("versions.id", ondelete="CASCADE"), primary_key=True)
    service_id = Column(String(255), primary_key=True)
    name       = Column(String(255), nullable=True)

    monday    = Column(SmallInteger, nullable=False)
    tuesday   = Column(SmallInteger, nullable=False)
    wednesday = Column(SmallInteger, nullable=False)
    thursday  = Column(SmallInteger, nullable=False)
    friday    = Column(SmallInteger, nullable=False)
    saturday  = Column(SmallInteger, nullable=False)
    sunday    = Column(SmallInteger, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date   = Column(Date, nullable=False)

    version = relationship("Version", back_populates="calendars")
    aux_calendar_assignments = relationship(
        "CalendarAuxCalendar",
        back_populates="calendar",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# AuxCalendars  — Hilfskalender, a named list of explicit dates, scoped to a Version
# ---------------------------------------------------------------------------

class AuxCalendar(Base):
    __tablename__ = "aux_calendars"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id = Column(UUID(as_uuid=True), ForeignKey("versions.id", ondelete="CASCADE"), nullable=False)
    name       = Column(String(255), nullable=False)

    version = relationship("Version", back_populates="aux_calendars")
    dates = relationship(
        "AuxCalendarDate",
        back_populates="aux_calendar",
        cascade="all, delete-orphan",
    )
    calendar_assignments = relationship(
        "CalendarAuxCalendar",
        back_populates="aux_calendar",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("version_id", "name", name="uq_aux_calendars_version_name"),
    )


# ---------------------------------------------------------------------------
# AuxCalendarDates  — individual date entries belonging to an AuxCalendar
# ---------------------------------------------------------------------------

class AuxCalendarDate(Base):
    __tablename__ = "aux_calendar_dates"

    aux_calendar_id = Column(
        UUID(as_uuid=True),
        ForeignKey("aux_calendars.id", ondelete="CASCADE"),
        primary_key=True,
    )
    date = Column(Date, primary_key=True)

    aux_calendar = relationship("AuxCalendar", back_populates="dates")


# ---------------------------------------------------------------------------
# CalendarAuxCalendar  — junction: assigns AuxCalendars to Calendars (Tagesarten)
# ---------------------------------------------------------------------------

class CalendarAuxCalendar(Base):
    __tablename__ = "calendar_aux_calendars"

    version_id      = Column(UUID(as_uuid=True), primary_key=True)
    service_id      = Column(String(255), primary_key=True)
    aux_calendar_id = Column(
        UUID(as_uuid=True),
        ForeignKey("aux_calendars.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # 1 = additional (zusätzlich), 2 = not (nicht)
    junction_type = Column(SmallInteger, nullable=False)

    calendar = relationship(
        "Calendar",
        back_populates="aux_calendar_assignments",
    )
    aux_calendar = relationship("AuxCalendar", back_populates="calendar_assignments")

    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "service_id"],
            ["calendars.version_id", "calendars.service_id"],
            name="fk_cal_aux_cal_calendar",
            ondelete="CASCADE",
        ),
    )


# ---------------------------------------------------------------------------
# Stops  — GTFS stops.txt entities, scoped to a Version
#
# Hierarchy:
#   Stop (station / top-level, parent_station IS NULL)
#     └─ Platform (Steig, location_type=0, parent_station = parent stop_id)
# ---------------------------------------------------------------------------

class Stop(Base):
    __tablename__ = "stops"

    version_id          = Column(UUID(as_uuid=True), ForeignKey("versions.id", ondelete="CASCADE"), primary_key=True)
    stop_id             = Column(String(255), primary_key=True)

    stop_code           = Column(String(255),  nullable=True)
    stop_name           = Column(Text,         nullable=True)
    tts_stop_name       = Column(Text,         nullable=True)
    stop_desc           = Column(Text,         nullable=True)
    stop_lat            = Column(Float,        nullable=True)
    stop_lon            = Column(Float,        nullable=True)
    zone_id             = Column(String(255),  nullable=True)
    stop_url            = Column(String(2048), nullable=True)
    location_type       = Column(SmallInteger, nullable=True)
    parent_station      = Column(String(255),  nullable=True)
    stop_timezone       = Column(String(64),   nullable=True)
    wheelchair_boarding = Column(SmallInteger, nullable=True)
    level_id            = Column(String(255),  nullable=True)
    platform_code       = Column(String(255),  nullable=True)
    stop_access         = Column(SmallInteger, nullable=True)

    version = relationship("Version", back_populates="stops")

    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "parent_station"],
            ["stops.version_id", "stops.stop_id"],
            name="fk_stops_parent_station",
            ondelete="CASCADE",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
    )


# ---------------------------------------------------------------------------
# Routes  — GTFS routes.txt entities, scoped to a Version
# ---------------------------------------------------------------------------

class Route(Base):
    __tablename__ = "routes"

    version_id          = Column(UUID(as_uuid=True), ForeignKey("versions.id", ondelete="CASCADE"), primary_key=True)
    route_id            = Column(String(255), primary_key=True)

    agency_id           = Column(String(255), nullable=True)
    route_short_name    = Column(String(255), nullable=True)
    route_long_name     = Column(String(255), nullable=True)
    route_desc          = Column(Text,        nullable=True)
    route_type          = Column(Integer,     nullable=False)
    route_url           = Column(String(2048), nullable=True)
    route_color         = Column(String(6),   nullable=True)
    route_text_color    = Column(String(6),   nullable=True)
    route_sort_order    = Column(Integer,     nullable=True)
    continuous_pickup   = Column(SmallInteger, nullable=True)
    continuous_drop_off = Column(SmallInteger, nullable=True)
    network_id          = Column(String(255), nullable=True)
    cemv_support        = Column(Integer,     nullable=True)

    version = relationship("Version", back_populates="routes")

    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "agency_id"],
            ["agencies.version_id", "agencies.agency_id"],
            name="fk_routes_agency",
            ondelete="SET NULL",
        ),
    )
