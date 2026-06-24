"""In-process agent event bus for dashboard SSE streaming."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any

_MAX_EVENTS = 500
_lock = Lock()
_events: deque[dict[str, Any]] = deque(maxlen=_MAX_EVENTS)
_next_id = 0


@dataclass
class AgentEvent:
    """Structured event emitted by orchestrator and workers."""

    event_type: str
    message: str
    application_id: int | None = None
    worker_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: int | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def emit_event(
    event_type: str,
    message: str,
    *,
    application_id: int | None = None,
    worker_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AgentEvent:
    """Record an event for SSE subscribers."""
    global _next_id
    with _lock:
        _next_id += 1
        event = AgentEvent(
            id=_next_id,
            event_type=event_type,
            message=message,
            application_id=application_id,
            worker_name=worker_name,
            metadata=metadata or {},
            timestamp=datetime.now(UTC).isoformat(),
        )
        _events.append(event.to_dict())
        return event


def list_events(*, after_id: int = 0, limit: int = 100) -> list[dict[str, Any]]:
    """Return events with id greater than after_id."""
    with _lock:
        items = [e for e in _events if e["id"] > after_id]
    return items[:limit]


def format_sse(event: dict[str, Any]) -> str:
    """Format a single event as an SSE data line."""
    payload = json.dumps(event)
    return f"data: {payload}\n\n"


def clear_events() -> None:
    """Reset event buffer (tests only)."""
    global _next_id
    with _lock:
        _events.clear()
        _next_id = 0
