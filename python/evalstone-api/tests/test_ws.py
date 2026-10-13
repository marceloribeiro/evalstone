import json
from pathlib import Path

import pytest
from starlette.websockets import WebSocketDisconnect

from app.services import events

REPORT = json.loads((Path(__file__).parent / "fixtures" / "rag-bot-ci-report.json").read_text())


def _ticket(client, project, token):
    r = client.post(
        f"/projects/{project['id']}/ws-ticket", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.text
    return r.json()["ticket"]


def _ws(client, project, token=None, *, ticket=None, project_id=None):
    ticket = ticket or _ticket(client, project, token)
    return client.websocket_connect(f"/ws/projects/{project_id or project['id']}?ticket={ticket}")


def test_tickets_are_minted_by_members_or_the_key_and_refused_otherwise(client, project, register):
    stranger_h, _ = register("s@x.example.com")
    assert (
        client.post(f"/projects/{project['id']}/ws-ticket", headers=stranger_h).status_code == 404
    )
    assert client.post(f"/projects/{project['id']}/ws-ticket").status_code == 401
    with pytest.raises(WebSocketDisconnect) as err, _ws(client, project, ticket="nope"):
        pass
    assert err.value.code == 1008
    # a ticket is single-use
    t = _ticket(client, project, project["headers"]["Authorization"].split()[1])
    with _ws(client, project, ticket=t) as ws:
        assert ws.receive_json()["event"] == "hello"
    with pytest.raises(WebSocketDisconnect), _ws(client, project, ticket=t):
        pass
    # and bound to its project
    other = client.post(
        f"/organizations/{project['org']['id']}/projects",
        json={"name": "Other"},
        headers=project["headers"],
    ).json()["id"]
    t = _ticket(client, project, project["headers"]["Authorization"].split()[1])
    with pytest.raises(WebSocketDisconnect), _ws(client, project, ticket=t, project_id=other):
        pass


def test_events_flow_from_a_run_push_to_the_socket(client, project):
    token = project["headers"]["Authorization"].split()[1]
    with _ws(client, project, token) as ws:
        assert ws.receive_json() == {"event": "hello", "project_id": project["id"]}
        ws.send_text("ping")
        assert ws.receive_json() == {"event": "pong"}
        r = client.post(f"/projects/{project['id']}/runs", json=REPORT, headers=project["headers"])
        assert r.status_code == 201
        msg = ws.receive_json()
        assert msg["event"] == "run.stored" and msg["project_id"] == project["id"]
        assert msg["client_run_id"] == REPORT["id"] and msg["result_count"] == 40 and msg["at"]
        # a push to ANOTHER project is not delivered here
        other = client.post(
            f"/organizations/{project['org']['id']}/projects",
            json={"name": "Other"},
            headers=project["headers"],
        ).json()["id"]
        client.post(f"/projects/{other}/runs", json=REPORT, headers=project["headers"])
        client.post(
            f"/projects/{project['id']}/labels",
            json={
                "labels": [
                    {"sample_id": "s", "output_hash": "0" * 16, "value": 1.0, "passed": True}
                ]
            },
            headers=project["headers"],
        )
        nxt = ws.receive_json()
        assert (
            nxt["event"] == "labels.stored" and nxt["count"] == 1
        )  # the other project's run was skipped


def test_ingest_key_can_listen(client, project):
    key = client.post(
        f"/projects/{project['id']}/ingest-keys", json={"name": "k"}, headers=project["headers"]
    ).json()["key"]
    with _ws(client, project, key) as ws:
        assert ws.receive_json()["event"] == "hello"


def test_publish_is_best_effort(monkeypatch, project):
    import uuid

    monkeypatch.setattr(
        events, "redis_client", lambda: (_ for _ in ()).throw(ConnectionError("redis down"))
    )
    assert events.publish(uuid.uuid4(), "run.stored", run_id=uuid.uuid4()) is False  # no raise
    with pytest.raises(ValueError):
        events.publish(uuid.uuid4(), "not.an.event")


def test_publish_serialises_uuids_and_hits_the_project_channel(project):
    import uuid

    import redis

    from app.config import get_settings

    pid = uuid.UUID(project["id"])
    sub = redis.Redis.from_url(get_settings().redis_url).pubsub()
    sub.subscribe(events.channel(pid))
    sub.get_message(timeout=1)  # the subscribe ack
    assert events.publish(pid, "alert.opened", alert_id=uuid.uuid4(), value=0.5) is True
    msg = sub.get_message(timeout=2)
    body = json.loads(msg["data"])
    assert (
        body["event"] == "alert.opened"
        and isinstance(body["alert_id"], str)
        and body["value"] == 0.5
    )
    sub.close()


def test_committed_openapi_is_current():
    from app.openapi_export import schema

    committed = json.loads((Path(__file__).parent.parent / "openapi.json").read_text())
    assert committed == schema(), "openapi.json is stale: run `just openapi` and commit it"
    assert "/ws/projects/{project_id}" not in committed["paths"]  # websockets are not in OpenAPI
    assert "/projects/{project_id}/runs" in committed["paths"]


def test_two_sockets_each_receive(client, project):
    token = project["headers"]["Authorization"].split()[1]
    with _ws(client, project, token) as a, _ws(client, project, token) as b:
        a.receive_json(), b.receive_json()
        client.post(f"/projects/{project['id']}/runs", json=REPORT, headers=project["headers"])
        assert (
            a.receive_json()["event"] == "run.stored" and b.receive_json()["event"] == "run.stored"
        )


# --- regressions from the #39 review ---------------------------------------------------------


def test_revoked_key_is_cut_off_by_the_recheck(client, project, monkeypatch):
    from app.routers import ws as ws_router

    monkeypatch.setattr(ws_router, "AUTH_RECHECK_S", 0.2)
    created = client.post(
        f"/projects/{project['id']}/ingest-keys", json={"name": "k"}, headers=project["headers"]
    ).json()
    with _ws(client, project, created["key"]) as ws:
        assert ws.receive_json()["event"] == "hello"
        client.delete(
            f"/projects/{project['id']}/ingest-keys/{created['id']}", headers=project["headers"]
        )
        with pytest.raises(WebSocketDisconnect) as err:
            ws.receive_json()
        assert err.value.code == 1008


def test_binary_and_junk_frames_are_ignored(client, project):
    token = project["headers"]["Authorization"].split()[1]
    with _ws(client, project, token) as ws:
        ws.receive_json()
        ws.send_bytes(b"\x00\x01keepalive")
        ws.send_text("not json at all")
        ws.send_text("ping")
        assert ws.receive_json() == {"event": "pong"}  # still alive


def test_hello_waits_for_the_subscription(client, project):
    """Events published right after `hello` are delivered (the SUBSCRIBE was acknowledged)."""
    import uuid

    token = project["headers"]["Authorization"].split()[1]
    with _ws(client, project, token) as ws:
        assert ws.receive_json()["event"] == "hello"
        events.publish(uuid.UUID(project["id"]), "traces.stored", count=7)
        assert ws.receive_json()["count"] == 7


def test_ticket_expires(client, project, monkeypatch):
    from app.services import events as ev

    token = project["headers"]["Authorization"].split()[1]
    t = _ticket(client, project, token)
    ev.redis_client().delete(ev._ticket_key(t))  # what the TTL does after 60 s
    with pytest.raises(WebSocketDisconnect), _ws(client, project, ticket=t):
        pass


def test_publish_uses_the_pooled_client(monkeypatch):
    import uuid

    from app.services import events as ev

    calls = []
    pool = ev.redis_client()
    monkeypatch.setattr(pool, "publish", lambda ch, msg: calls.append(ch) or 1)
    assert ev.publish(uuid.uuid4(), "traces.stored", count=1) is True and len(calls) == 1
