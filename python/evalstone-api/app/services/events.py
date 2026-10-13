"""Live updates: services publish project events to Redis; the WebSocket route fans them out.

One channel per project (`evalstone:project:<id>`). Publishing is best-effort — a Redis
hiccup never fails the request that produced the event (the database is the truth; the
socket is a nudge). Payloads are small and self-describing: {"event", "at", ...fields}.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import redis

from app.config import get_settings

log = logging.getLogger(__name__)

EVENTS = (
    "run.stored",
    "calibration.finished",
    "monitor.scored",
    "alert.opened",
    "alert.resolved",
    "traces.stored",
    "labels.stored",
)


def channel(project_id: uuid.UUID | str) -> str:
    return f"evalstone:project:{project_id}"


def _client() -> redis.Redis:
    return redis.Redis.from_url(
        get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1
    )


def publish(project_id: uuid.UUID | str, event: str, **fields: Any) -> bool:
    """PUBLISH one event; returns whether Redis accepted it (never raises)."""
    if event not in EVENTS:
        raise ValueError(f"unknown event {event!r}")
    payload = {"event": event, "project_id": str(project_id), "at": datetime.now(UTC).isoformat()}
    payload.update({k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in fields.items()})
    try:
        client = _client()
        try:
            client.publish(channel(project_id), json.dumps(payload, default=str))
        finally:
            client.close()
        return True
    except Exception as exc:
        log.warning("event %s not published for project %s: %s", event, project_id, exc)
        return False
