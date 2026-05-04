from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, UniqueConstraint
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
