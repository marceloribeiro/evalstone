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
    an Evalstone task. Observed on the real Redis the tests use, not read back from the config:
    declaring the queue writes the binding under the prefix and nowhere else."""
    import redis

    from app.config import get_settings
    from app.services import events

    prefix = get_settings().redis_key_prefix
    assert prefix.endswith(":")
    assert celery_app.conf.broker_transport_options["global_keyprefix"] == prefix
    assert celery_app.conf.result_backend_transport_options["global_keyprefix"] == prefix
    r = redis.Redis.from_url(get_settings().celery_broker_url)
    r.delete(f"{prefix}_kombu.binding.celery", "_kombu.binding.celery")
    with celery_app.connection_for_write() as conn:
        celery_app.amqp.queues["celery"](conn.default_channel).declare()
    assert r.exists(f"{prefix}_kombu.binding.celery") == 1
    assert r.exists("_kombu.binding.celery") == 0
    # the pub/sub channel and the ws-ticket key come from the same setting
    assert events.channel("p1") == f"{prefix}project:p1"


def test_prefix_is_normalised_and_required_outside_dev(monkeypatch):
    from app.config import Settings

    assert Settings(redis_key_prefix="demo").redis_key_prefix == "demo:"
    import pytest

    with pytest.raises(ValueError, match="REDIS_KEY_PREFIX"):
        Settings(
            app_env="production",
            jwt_secret="x" * 40,
            docs_password="not-the-default-at-all",
            provider_creds_key="JD4D6kRkv9sw5Qj5xrr1CZx-3aPrDjkKshMYZgUGLiU=",
            redis_key_prefix="",
        )
