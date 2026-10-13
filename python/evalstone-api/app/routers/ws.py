"""`GET /ws/projects/{project_id}?token=…` — the project's live events over a WebSocket.

Browsers cannot set headers on a WebSocket handshake, so the credential rides in the query
string: a member's JWT or the project's `es_…` ingest key. The socket subscribes to the
project's Redis channel and forwards every event as one JSON text frame. A `ping` text frame
from the client is answered with `pong`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials

from app.config import get_settings
from app.db import SessionLocal
from app.deps import get_project_actor
from app.errors import DomainError
from app.services import events

router = APIRouter(tags=["live"])

POLICY_VIOLATION = 1008
INTERNAL_ERROR = 1011


def _authorize(project_id: uuid.UUID, token: str) -> None:
    """Same rule as the data-plane routes: a member, or this project's ingest key."""
    db = SessionLocal()
    try:
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        get_project_actor(project_id, creds, db)
    finally:
        db.close()


@router.websocket("/ws/projects/{project_id}")
async def project_events(
    websocket: WebSocket, project_id: uuid.UUID, token: str = Query(..., min_length=1)
):
    try:
        await asyncio.to_thread(_authorize, project_id, token)
    except DomainError as err:
        await websocket.close(code=POLICY_VIOLATION, reason=err.detail[:120])
        return
    await websocket.accept()
    client = aioredis.from_url(get_settings().redis_url, socket_connect_timeout=2)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(events.channel(project_id))
        await websocket.send_json({"event": "hello", "project_id": str(project_id)})
        forward = asyncio.create_task(_forward(pubsub, websocket))
        listen = asyncio.create_task(_listen(websocket))
        done, pending = await asyncio.wait({forward, listen}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                with contextlib.suppress(Exception):
                    await websocket.close(code=INTERNAL_ERROR, reason=type(exc).__name__)
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(events.channel(project_id))
            await pubsub.aclose()
            await client.aclose()


async def _forward(pubsub: aioredis.client.PubSub, websocket: WebSocket) -> None:
    async for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        data = message["data"]
        text = data.decode() if isinstance(data, bytes) else str(data)
        await websocket.send_text(text)


async def _listen(websocket: WebSocket) -> None:
    """Keep the socket alive and answer pings; the client's close ends the session."""
    while True:
        text = await websocket.receive_text()
        if text.strip() == "ping":
            await websocket.send_json({"event": "pong"})
        else:
            with contextlib.suppress(ValueError):
                json.loads(text)  # tolerated and ignored: the socket is server → client
