from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from composegtfs.config import settings
from composegtfs.database import get_session
from composegtfs.models import User

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def _decode_token(token: str) -> str:
    """Decode JWT and return the subject (username). Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        sub: str | None = payload.get("sub")
        if sub is None:
            raise ValueError("Missing subject")
        return sub
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ---------------------------------------------------------------------------
# Current-user dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    token: str = Depends(_oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    username = _decode_token(token)
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


async def get_current_superuser(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser required")
    return user


# ---------------------------------------------------------------------------
# Login helper used by the endpoint
# ---------------------------------------------------------------------------

async def authenticate_user(username: str, password: str, session: AsyncSession) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ---------------------------------------------------------------------------
# Sliding-token middleware
# ---------------------------------------------------------------------------

class SlidingTokenMiddleware(BaseHTTPMiddleware):
    """Attach a fresh token in the ``X-New-Token`` response header whenever
    an authenticated request carries a JWT that has consumed more than half
    of its lifetime.  The frontend reads this header and silently replaces
    the stored token so that active sessions never expire.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return response

        token = auth[len("Bearer "):]
        try:
            payload = jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.algorithm],
            )
            exp: float | None = payload.get("exp")
            sub: str | None = payload.get("sub")
            if exp and sub:
                now = datetime.now(timezone.utc).timestamp()
                lifetime = settings.access_token_expire_minutes * 60
                time_remaining = exp - now
                if 0 < time_remaining < lifetime / 2:
                    new_token = create_access_token(subject=sub)
                    response.headers["X-New-Token"] = new_token
        except Exception:
            # Never disrupt a response because of token introspection
            pass

        return response
