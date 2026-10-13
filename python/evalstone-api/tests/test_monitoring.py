import httpx
import pytest
import respx

from app.services import monitoring as svc
from app.services import providers as provider_svc


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(provider_svc, "_resolve", lambda host: ["93.184.216.34"])


def _p(project, suffix=""):
    return f"/projects/{project['id']}" + suffix


def _catalog(client, project, key, type_, params):
    r = client.post(
        f"/organizations/{project['org']['id']}/checks",
        json={"key": key, "type": type_, "params": params},
        headers=project["headers"],
    )
    assert r.status_code == 201, r.text


def _traces(n, *, start=0, bad=()):
    return [
        {
            "id": f"t{i}",
            "input": f"question {i}",
            "output": "no idea" if i in bad else f"Paris is the answer {i}",
            "tags": ["prod"],
            "latency_ms": 12.5,
        }
        for i in range(start, start + n)
    ]


def _key(client, project):
    return client.post(
        _p(project, "/ingest-keys"), json={"name": "app"}, headers=project["headers"]
    ).json()["key"]


def test_trace_ingest_is_idempotent_and_listable(client, project):
    kh = {"Authorization": f"Bearer {_key(client, project)}"}
    r = client.post(_p(project, "/traces"), json={"traces": _traces(3)}, headers=kh)
    assert r.status_code == 200 and r.json() == {"stored": 3}
    again = client.post(_p(project, "/traces"), json={"traces": _traces(3)}, headers=kh)
    assert again.json() == {"stored": 0}  # retried push
    page = client.get(_p(project, "/traces"), headers=project["headers"]).json()
    assert page["total"] == 3 and {t["client_id"] for t in page["items"]} == {"t0", "t1", "t2"}
    t = page["items"][0]
    assert 0.0 <= t["sample_bucket"] < 1.0 and t["output_hash"] and t["tags"] == ["prod"]
    flagged = client.post(
        _p(project, f"/traces/{t['id']}/flag"), json={}, headers=project["headers"]
    ).json()
    assert flagged["flagged"] is True
    assert (
        client.get(
            _p(project, "/traces"), params={"flagged": True}, headers=project["headers"]
        ).json()["total"]
        == 1
    )
    big = [{"input": "x" * (svc.MAX_TRACE_BYTES + 1)}]
    assert client.post(_p(project, "/traces"), json={"traces": big}, headers=kh).status_code == 422


def test_sample_bucket_is_stable_per_trace():
    import uuid

    pid = uuid.uuid4()
    assert svc.sample_bucket(pid, "t1") == svc.sample_bucket(pid, "t1")
    assert svc.sample_bucket(pid, "t1") != svc.sample_bucket(pid, "t2")
    buckets = [svc.sample_bucket(pid, f"t{i}") for i in range(2000)]
    assert 0.05 < sum(b < 0.1 for b in buckets) / 2000 < 0.15  # a 10% rate samples ~10%


def test_monitor_validation(client, project):
    h = project["headers"]
    _catalog(client, project, "has-paris", "contains", {"needles": ["Paris"]})
    base = {"name": "m", "check_keys": ["has-paris"], "alert_policy": {"threshold": 0.9}}
    bad_check = client.post(
        _p(project, "/monitors"), json={**base, "check_keys": ["nope"]}, headers=h
    )
    assert (
        bad_check.status_code == 422
        and "not in the organization's check catalog" in bad_check.json()["detail"]
    )
    bad_hook = client.post(
        _p(project, "/monitors"), json={**base, "webhook_url": "http://169.254.169.254/"}, headers=h
    )
    assert bad_hook.status_code == 422
    ok = client.post(
        _p(project, "/monitors"),
        json={**base, "webhook_url": "https://hooks.example.com/x"},
        headers=h,
    )
    assert ok.status_code == 201, ok.text
    m = ok.json()
    assert m["alert_policy"] == {
        "metric": "pass_rate",
        "threshold": 0.9,
        "window_minutes": 60,
        "min_n": 20,
    }
    assert m["sample_rate"] == 0.1 and m["status"] == "active"
    upd = client.patch(
        _p(project, f"/monitors/{m['id']}"),
        json={"status": "paused", "sample_rate": 1.0},
        headers=h,
    )
    assert upd.json()["status"] == "paused" and upd.json()["sample_rate"] == 1.0
    member_h = project["headers"]
    assert client.get(_p(project, "/monitors"), headers=member_h).json()[0]["id"] == m["id"]


def test_scoring_deterministic_checks_and_alert_lifecycle(client, project, db):
    """20 traces, 4 bad → pass rate 0.8 < 0.9 → one alert + webhook; recovery resolves it."""
    h = project["headers"]
    _catalog(client, project, "has-paris", "contains", {"needles": ["Paris"]})
    hook = "https://hooks.example.com/alerts"
    m = client.post(
        _p(project, "/monitors"),
        json={
            "name": "prod answers",
            "check_keys": ["has-paris"],
            "sample_rate": 1.0,
            "alert_policy": {"threshold": 0.9, "window_minutes": 60, "min_n": 10},
            "webhook_url": hook,
        },
        headers=h,
    ).json()
    kh = {"Authorization": f"Bearer {_key(client, project)}"}
    client.post(_p(project, "/traces"), json={"traces": _traces(20, bad={1, 5, 9, 13})}, headers=kh)
    with respx.mock:
        route = respx.post(hook).mock(return_value=httpx.Response(200))
        result = svc.score_monitor(db, __import__("uuid").UUID(m["id"]))
    assert result["scored"] == 20 and result["errors"] == 0
    assert result["alert"]["state"] == "opened" and result["alert"]["value"] == pytest.approx(0.8)
    assert route.call_count == 1
    body = route.calls[0].request.content
    assert (
        b'"event": "evalstone.alert.opened"' in body or b'"event":"evalstone.alert.opened"' in body
    )
    window = client.get(_p(project, f"/monitors/{m['id']}/window"), headers=h).json()
    assert window["n"] == 20 and window["pass_rate"] == pytest.approx(0.8)
    alerts = client.get(_p(project, "/alerts"), params={"open": True}, headers=h).json()
    assert len(alerts) == 1 and alerts[0]["notified_at"] and alerts[0]["n"] == 20
    # a second tick with nothing new keeps the one open alert
    with respx.mock:
        route = respx.post(hook).mock(return_value=httpx.Response(200))
        again = svc.score_monitor(db, __import__("uuid").UUID(m["id"]))
    assert again["scored"] == 0 and again["alert"]["state"] == "open" and route.call_count == 0
    # 40 good traces → pass rate 0.93 → resolved
    client.post(_p(project, "/traces"), json={"traces": _traces(40, start=100)}, headers=kh)
    with respx.mock:
        recovered = svc.score_monitor(db, __import__("uuid").UUID(m["id"]))
    assert recovered["alert"]["state"] == "resolved"
    assert client.get(_p(project, "/alerts"), params={"open": True}, headers=h).json() == []
    assert client.get(_p(project, "/alerts"), headers=h).json()[0]["resolved_at"]


def test_sampling_scores_only_the_bucketed_traces(client, project, db):
    import uuid

    h = project["headers"]
    _catalog(client, project, "has-paris", "contains", {"needles": ["Paris"]})
    m = client.post(
        _p(project, "/monitors"),
        json={
            "name": "m",
            "check_keys": ["has-paris"],
            "sample_rate": 0.25,
            "alert_policy": {"threshold": 0.5, "min_n": 1000},
        },
        headers=h,
    ).json()
    kh = {"Authorization": f"Bearer {_key(client, project)}"}
    client.post(_p(project, "/traces"), json={"traces": _traces(200)}, headers=kh)
    result = svc.score_monitor(db, uuid.UUID(m["id"]))
    expected = sum(
        1 for i in range(200) if svc.sample_bucket(uuid.UUID(project["id"]), f"t{i}") < 0.25
    )
    assert result["scored"] == expected and 30 < expected < 70
    assert result["alert"] is None  # min_n not reached


@respx.mock
def test_judge_checks_score_with_the_orgs_provider(client, project, db, monkeypatch):
    import uuid

    h, org = project["headers"], project["org"]
    upstream = "https://judge.example.com/v1"
    client.post(
        f"/organizations/{org['id']}/providers",
        json={"name": "judge", "adapter": "openai", "api_key": "sk-judge", "base_url": upstream},
        headers=h,
    )
    client.put(_p(project, "/judge-settings"), json={"default_model": "judge/small"}, headers=h)
    _catalog(client, project, "helpful", "judge", {"rubric": "Is it helpful?"})
    m = client.post(
        _p(project, "/monitors"),
        json={
            "name": "j",
            "check_keys": ["helpful"],
            "sample_rate": 1.0,
            "alert_policy": {"threshold": 0.5, "min_n": 100},
        },
        headers=h,
    ).json()
    kh = {"Authorization": f"Bearer {_key(client, project)}"}
    client.post(_p(project, "/traces"), json={"traces": _traces(3)}, headers=kh)
    route = respx.post(upstream + "/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "small",
                "choices": [{"message": {"content": '{"score": 4, "reason": "ok"}'}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 8},
            },
        )
    )
    result = svc.score_monitor(db, uuid.UUID(m["id"]))
    assert result["scored"] == 3 and result["errors"] == 0 and route.call_count == 3
    assert (
        route.calls[0].request.headers["Authorization"] == "Bearer sk-judge"
    )  # the org's key, server-side
    scores = db.query(__import__("app.models", fromlist=["TraceScore"]).TraceScore).all()
    assert all(s.passed and s.score == 0.75 for s in scores)


def test_monitor_without_a_usable_judge_records_the_error(client, project, db):
    import uuid

    h = project["headers"]
    _catalog(client, project, "helpful", "judge", {"rubric": "r"})  # no provider configured
    m = client.post(
        _p(project, "/monitors"),
        json={
            "name": "j",
            "check_keys": ["helpful"],
            "sample_rate": 1.0,
            "alert_policy": {"threshold": 0.5, "min_n": 1},
        },
        headers=h,
    ).json()
    kh = {"Authorization": f"Bearer {_key(client, project)}"}
    client.post(_p(project, "/traces"), json={"traces": _traces(2)}, headers=kh)
    result = svc.score_monitor(db, uuid.UUID(m["id"]))
    assert result["scored"] == 2 and result["errors"] == 2  # errored verdicts, not a crash
    assert result["alert"] is None  # errors are not verdicts: n stays 0


def test_beat_task_enqueues_active_monitors(client, project, monkeypatch):
    from app import tasks
    from app.worker import celery_app

    h = project["headers"]
    _catalog(client, project, "has-paris", "contains", {"needles": ["Paris"]})
    body = {"name": "m", "check_keys": ["has-paris"], "alert_policy": {"threshold": 0.9}}
    a = client.post(_p(project, "/monitors"), json=body, headers=h).json()["id"]
    b = client.post(_p(project, "/monitors"), json=body, headers=h).json()["id"]
    client.patch(_p(project, f"/monitors/{b}"), json={"status": "paused"}, headers=h)
    enqueued = []
    monkeypatch.setattr(tasks.score_monitor, "delay", lambda mid: enqueued.append(mid))
    assert tasks.score_monitors() == 1 and enqueued == [a]
    assert "score-monitors" in celery_app.conf.beat_schedule
    r = client.post(_p(project, f"/monitors/{a}/score"), headers=h)
    assert r.status_code == 200 and enqueued == [a, a]


def test_webhook_failure_is_recorded_on_the_alert(client, project, db):
    import uuid

    h = project["headers"]
    _catalog(client, project, "has-paris", "contains", {"needles": ["Paris"]})
    hook = "https://hooks.example.com/down"
    m = client.post(
        _p(project, "/monitors"),
        json={
            "name": "m",
            "check_keys": ["has-paris"],
            "sample_rate": 1.0,
            "alert_policy": {"threshold": 0.9, "min_n": 5},
            "webhook_url": hook,
        },
        headers=h,
    ).json()
    kh = {"Authorization": f"Bearer {_key(client, project)}"}
    client.post(_p(project, "/traces"), json={"traces": _traces(10, bad={0, 1, 2})}, headers=kh)
    with respx.mock:
        respx.post(hook).mock(return_value=httpx.Response(503, text="nope"))
        svc.score_monitor(db, uuid.UUID(m["id"]))
    alert = client.get(_p(project, "/alerts"), headers=h).json()[0]
    assert alert["notified_at"] is None and "503" in alert["notify_error"]
