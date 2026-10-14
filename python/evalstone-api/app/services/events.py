"""Live updates: services publish project events to Redis; the WebSocket route fans them out.

One channel per project (`<REDIS_KEY_PREFIX>project:<id>`). Publishing is best-effort — a Redis
hiccup never fails the request that produced the event (the database is the truth; the
socket is a nudge). Payloads are small and self-describing: {"event", "at", ...fields}.
One pooled client serves every caller (health, publish, tickets): no connect per event.
"""

from __future__ import annotations

import json
import logging
import secrets
import uuid
from datetime import UTC, datetime
from functools import lru_cache
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
TICKET_TTL_S = 60  # a ws ticket is minted over the authenticated REST surface and used once


def channel(project_id: uuid.UUID | str) -> str:
    return f"{get_settings().redis_key_prefix}project:{project_id}"


@lru_cache
def redis_client() -> redis.Redis:
    """The process-wide pooled client (thread-safe); short timeouts keep every caller snappy."""
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
        redis_client().publish(channel(project_id), json.dumps(payload, default=str))
        return True
    except Exception as exc:
        log.warning("event %s not published for project %s: %s", event, project_id, exc)
        return False


# --- websocket tickets ------------------------------------------------------------------------


def _ticket_key(ticket: str) -> str:
    return f"{get_settings().redis_key_prefix}ws-ticket:{ticket}"


def mint_ticket(project_id: uuid.UUID, credential: str) -> str:
    """A one-time, 60-second ticket standing in for `credential` on the socket handshake,
    so the real JWT / ingest key never appears in a URL or an access log."""
    ticket = secrets.token_urlsafe(32)
    redis_client().set(
        _ticket_key(ticket),
        json.dumps({"project_id": str(project_id), "credential": credential}),
        ex=TICKET_TTL_S,
    )
    return ticket


def redeem_ticket(ticket: str) -> tuple[uuid.UUID, str] | None:
    """(project_id, credential) for a live ticket — consumed on read; None when unknown/used."""
    client = redis_client()
    raw = client.getdel(_ticket_key(ticket))
    if not raw:
        return None
    data = json.loads(raw)
    return uuid.UUID(data["project_id"]), data["credential"]
