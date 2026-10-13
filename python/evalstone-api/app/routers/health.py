"""Liveness and readiness (docs/API.md §1). No auth; `/health` never touches a dependency."""

import redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db

router = APIRouter(tags=["health"])

PROBE_TIMEOUT_S = 1.0
PROBE_TIMEOUT_MS = int(PROBE_TIMEOUT_S * 1000)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    """503 when PostgreSQL or Redis (the Celery broker) is unreachable; says which."""
    checks: dict[str, str] = {}
    try:
        db.execute(text(f"SET LOCAL statement_timeout = {PROBE_TIMEOUT_MS}"))
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "down"
    finally:
        db.rollback()
    client = redis.Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=PROBE_TIMEOUT_S,
        socket_timeout=PROBE_TIMEOUT_S,  # a stalled broker returns 503, not a hung probe
    )
    try:
        client.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "down"
    finally:
        client.close()
    if any(v != "ok" for v in checks.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", **checks},
        )
    return {"status": "ready", **checks}
