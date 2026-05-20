"""GTFS Export router.

POST /api/gtfs/export/{version_id}
-----------------------------------
Triggers a GTFS export and streams progress as Server-Sent Events (SSE).

Request body (JSON)
-------------------
{
    "route_ids":  ["R1", "R2", ...],   // list of route IDs to include
    "date_from":  "YYYY-MM-DD",
    "date_to":    "YYYY-MM-DD"
}

Response: text/event-stream
Each SSE event carries a JSON-encoded ExportEvent:

    data: {"type": "info",    "message": "...", "file": null}
    data: {"type": "success", "message": "...", "file": "stops.txt"}
    data: {"type": "done",    "message": "...", "file": null,
           "payload": "<base64-encoded ZIP>", "filename": "gtfs_<uuid>.zip"}

The client downloads the ZIP by decoding the base64 payload from the "done"
event.
"""

from __future__ import annotations

import json
import uuid
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from composegtfs.database import get_session
from composegtfs.permissions import Permission, require
from composegtfs.services.gtfs_export import run_export

router = APIRouter(prefix="/api/gtfs", tags=["gtfs-export"])


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class ExportRequest(BaseModel):
    route_ids:          list[str]
    date_from:          date
    date_to:            date
    export_all_stops:   bool = False
    export_shapes:      bool = True
    prefer_global_ids:  bool = False


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------

def _sse(event_dict: dict) -> str:
    """Encode a dict as a single SSE data line."""
    return f"data: {json.dumps(event_dict, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/export/{version_id}",
    summary="Run GTFS export and stream progress via SSE",
    dependencies=[require(Permission.GTFS_EXPORT)],
    response_class=StreamingResponse,
)
async def gtfs_export(
    version_id: uuid.UUID,
    body: ExportRequest,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    async def _generate():
        async for event in run_export(
            version_id=version_id,
            route_ids=body.route_ids,
            date_from=body.date_from,
            date_to=body.date_to,
            export_all_stops=body.export_all_stops,
            export_shapes=body.export_shapes,
            prefer_global_ids=body.prefer_global_ids,
            session=session,
        ):
            yield _sse(event)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable Nginx buffering for SSE
        },
    )
