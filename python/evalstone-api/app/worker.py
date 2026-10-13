"""Celery app. `just workers` / `just beat` run it; tests set CELERY_TASK_ALWAYS_EAGER=1."""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "evalstone",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)
celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # judge and calibration jobs are long; do not hoard
    beat_schedule={
        # proves beat → broker → worker end to end; real schedules come with their slices
        "heartbeat": {"task": "app.tasks.heartbeat", "schedule": 300.0},
    },
)
