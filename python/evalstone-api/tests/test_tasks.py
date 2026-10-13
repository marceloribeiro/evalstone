from app import tasks
from app.worker import celery_app


def test_ping_round_trips_eagerly():
    assert celery_app.conf.task_always_eager is True
    assert tasks.ping.delay("x").get() == "pong:x"


def test_heartbeat_is_scheduled_and_runs():
    assert "heartbeat" in celery_app.conf.beat_schedule
    assert tasks.heartbeat.delay().get() == "alive"
