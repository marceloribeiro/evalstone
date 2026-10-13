"""Liveness and readiness (docs/API.md §1). No auth; `/health` never touches a dependency."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import events

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
    try:
        events.redis_client().ping()  # the pooled client: 1 s connect/read timeouts
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "down"
    if any(v != "ok" for v in checks.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", **checks},
        )
    return {"status": "ready", **checks}
