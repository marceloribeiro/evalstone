"""Celery tasks. Domain tasks (judging, calibration, monitors) land with their slices."""

import logging

from app.worker import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.ping")
def ping(payload: str = "ping") -> str:
    """Round-trips a string through the broker; `just workers` + the console observe it."""
    return f"pong:{payload}"


@celery_app.task(name="app.tasks.heartbeat")
def heartbeat() -> str:
    """Scheduled by beat every 5 minutes so a silent scheduler shows up in the logs."""
    log.info("heartbeat")
    return "alive"


@celery_app.task(name="app.tasks.calibrate")
def calibrate(calibration_id: str) -> str:
    """Compute one judge calibration (queued by POST /projects/{id}/calibrations)."""
    import uuid

    from app.db import SessionLocal
    from app.services import calibration as svc

    db = SessionLocal()
    try:
        row = svc.run_job(db, uuid.UUID(calibration_id))
        return row.status
    finally:
        db.close()


@celery_app.task(name="app.tasks.score_monitor")
def score_monitor(monitor_id: str) -> dict:
    """Score one monitor's sampled traces and evaluate its alert policy."""
    import uuid

    from app.db import SessionLocal
    from app.services import monitoring as svc

    db = SessionLocal()
    try:
        return svc.score_monitor(db, uuid.UUID(monitor_id))
    finally:
        db.close()


@celery_app.task(name="app.tasks.score_monitors")
def score_monitors() -> int:
    """Beat, every minute: one score_monitor task per active monitor."""
    from app.db import SessionLocal
    from app.services import monitoring as svc

    db = SessionLocal()
    try:
        ids = svc.active_monitor_ids(db)
    finally:
        db.close()
    for mid in ids:
        score_monitor.delay(str(mid))
    return len(ids)
