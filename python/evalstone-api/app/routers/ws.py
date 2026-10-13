"""`GET /ws/projects/{project_id}?ticket=…` — the project's live events over a WebSocket.

Browsers cannot set headers on a WebSocket handshake and a URL ends up in access logs, so
the credential never travels on the socket: the client first calls
`POST /projects/{id}/ws-ticket` with its normal bearer (a member's JWT or the project's
`es_…` key) and receives a one-time 60-second ticket. The socket redeems the ticket,
re-checks the credential every AUTH_RECHECK_S (a revoked key or an expired token ends the
session), subscribes to the project's Redis channel and forwards every event as one JSON
text frame. A `ping` text frame is answered with `pong`; other frames are ignored.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials

from app.config import get_settings
from app.db import SessionLocal
from app.deps import ProjectActor, bearer, get_project_actor
from app.errors import DomainError, Unauthorized
from app.services import events

router = APIRouter(tags=["live"])

POLICY_VIOLATION = 1008
INTERNAL_ERROR = 1011
AUTH_RECHECK_S = 60.0


@router.post("/projects/{project_id}/ws-ticket")
def ws_ticket(
    actor: ProjectActor = Depends(get_project_actor),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    """A one-time ticket for `GET /ws/projects/{id}?ticket=…` (valid 60 s)."""
    ticket = events.mint_ticket(actor.project.id, credentials.credentials)
    return {"ticket": ticket, "expires_in": events.TICKET_TTL_S}


def _authorize(project_id: uuid.UUID, credential: str) -> None:
    """Same rule as the data-plane routes: a member, or this project's ingest key."""
    db = SessionLocal()
    try:
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=credential)
        get_project_actor(project_id, creds, db)
    finally:
        db.close()


@router.websocket("/ws/projects/{project_id}")
async def project_events(
    websocket: WebSocket, project_id: uuid.UUID, ticket: str = Query(..., min_length=1)
):
    redeemed = await asyncio.to_thread(events.redeem_ticket, ticket)
    try:
        if redeemed is None or redeemed[0] != project_id:
            raise Unauthorized("unknown, used or expired ticket")
        credential = redeemed[1]
        await asyncio.to_thread(_authorize, project_id, credential)
    except DomainError as err:
        await websocket.close(code=POLICY_VIOLATION, reason=err.detail[:120])
        return
    await websocket.accept()
    client = aioredis.from_url(get_settings().redis_url, socket_connect_timeout=2)
    pubsub = client.pubsub()
    tasks: list[asyncio.Task] = []
    try:
        await pubsub.subscribe(events.channel(project_id))
        await _wait_subscribed(pubsub)  # nothing published after `hello` can be missed
        await websocket.send_json({"event": "hello", "project_id": str(project_id)})
        tasks = [
            asyncio.create_task(_forward(pubsub, websocket)),
            asyncio.create_task(_listen(websocket)),
            asyncio.create_task(_recheck(project_id, credential)),
        ]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if isinstance(exc, DomainError):
                with contextlib.suppress(Exception):
                    await websocket.close(code=POLICY_VIOLATION, reason=exc.detail[:120])
            elif exc is not None and not isinstance(exc, WebSocketDisconnect):
                with contextlib.suppress(Exception):
                    await websocket.close(code=INTERNAL_ERROR, reason=type(exc).__name__)
    finally:
        for task in tasks:  # also on a cancelled handler (server shutdown)
            if not task.done():
                task.cancel()
                with contextlib.suppress(BaseException):
                    await task
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(events.channel(project_id))
        with contextlib.suppress(Exception):
            await pubsub.aclose()
        with contextlib.suppress(Exception):
            await client.aclose()


async def _wait_subscribed(pubsub: aioredis.client.PubSub) -> None:
    while True:
        message = await pubsub.get_message(ignore_subscribe_messages=False, timeout=5.0)
        if message is None:
            raise RuntimeError("Redis did not confirm the subscription")
        if message.get("type") == "subscribe":
            return


async def _forward(pubsub: aioredis.client.PubSub, websocket: WebSocket) -> None:
    async for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        data = message["data"]
        await websocket.send_text(data.decode() if isinstance(data, bytes) else str(data))


async def _listen(websocket: WebSocket) -> None:
    """Keep the socket alive and answer pings; any other frame (text or binary) is ignored."""
    while True:
        message = await websocket.receive()
        if message.get("type") == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code", 1000))
        if message.get("text", "").strip() == "ping":
            await websocket.send_json({"event": "pong"})


async def _recheck(project_id: uuid.UUID, credential: str) -> None:
    """Re-run the authorization rule periodically; a failure ends the session (1008)."""
    while True:
        await asyncio.sleep(AUTH_RECHECK_S)
        await asyncio.to_thread(_authorize, project_id, credential)
