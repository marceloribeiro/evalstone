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
