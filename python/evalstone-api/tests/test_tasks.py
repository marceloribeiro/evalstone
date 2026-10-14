from app import tasks
from app.worker import celery_app


def test_ping_round_trips_eagerly():
    assert celery_app.conf.task_always_eager is True
    assert tasks.ping.delay("x").get() == "pong:x"


def test_heartbeat_is_scheduled_and_runs():
    assert "heartbeat" in celery_app.conf.beat_schedule
    assert tasks.heartbeat.delay().get() == "alive"


def test_every_celery_key_is_namespaced():
    """A shared Redis index: another app's worker on the default `celery` queue must never see
    an Evalstone task, so the broker and the result backend prefix every key."""
    assert celery_app.conf.broker_transport_options["global_keyprefix"] == "evalstone:"
    assert celery_app.conf.result_backend_transport_options["global_keyprefix"] == "evalstone:"
