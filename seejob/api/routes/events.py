"""Server-sent events stream for agent orchestration dashboard."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from seejob.services.events import format_sse, list_events

router = APIRouter()


async def _event_generator(after_id: int = 0):
    """Poll in-process event bus and yield SSE frames."""
    cursor = after_id
    while True:
        events = list_events(after_id=cursor)
        for event in events:
            cursor = event["id"]
            yield format_sse(event)
        await asyncio.sleep(1)


@router.get("/stream")
async def stream_events(after_id: int = 0) -> StreamingResponse:
    """Stream agent events as Server-Sent Events for the dashboard."""
    return StreamingResponse(
        _event_generator(after_id=after_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("")
def get_recent_events(after_id: int = 0, limit: int = 100) -> list[dict]:
    """Return recent agent events (polling fallback)."""
    return list_events(after_id=after_id, limit=limit)
