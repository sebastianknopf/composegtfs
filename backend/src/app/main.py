from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import SlidingTokenMiddleware
from app.config import settings
from app.routers import auth as auth_router
from app.routers import groups as groups_router
from app.routers import permissions as permissions_router
from app.routers import settings as settings_router
from app.routers import users as users_router
from app.routers import versions as versions_router
from app.routers import agencies as agencies_router
from app.routers.calendars import aux_calendars_router, calendars_router
from app.routers import stops as stops_router
from app.routers import routes as routes_router
from app.routers import schedule as schedule_router

app = FastAPI(
    title="composegtfs",
    version="0.1.0",
    docs_url="/api/docs" if settings.docs_enabled else None,
    redoc_url="/api/redoc" if settings.docs_enabled else None,
    openapi_url="/api/openapi.json" if settings.docs_enabled else None,
)

if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-New-Token"],
    )

app.add_middleware(SlidingTokenMiddleware)

app.include_router(auth_router.router)
app.include_router(settings_router.router)
app.include_router(users_router.router)
app.include_router(groups_router.router)
app.include_router(permissions_router.router)
app.include_router(versions_router.router)
app.include_router(agencies_router.router)
app.include_router(calendars_router)
app.include_router(aux_calendars_router)
app.include_router(stops_router.router)
app.include_router(routes_router.router)
app.include_router(schedule_router.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
