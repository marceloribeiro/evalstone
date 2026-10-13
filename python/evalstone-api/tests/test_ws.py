import json
from pathlib import Path

import pytest
from starlette.websockets import WebSocketDisconnect

from app.services import events

REPORT = json.loads((Path(__file__).parent / "fixtures" / "rag-bot-ci-report.json").read_text())


def _ws(client, project, token):
    return client.websocket_connect(f"/ws/projects/{project['id']}?token={token}")


def test_socket_requires_a_member_or_the_projects_key(client, project, register):
    stranger_h, _ = register("s@x.example.com")
    with (
        pytest.raises(WebSocketDisconnect) as err,
        _ws(client, project, stranger_h["Authorization"].split()[1]),
    ):
        pass
    assert err.value.code == 1008
    with pytest.raises(WebSocketDisconnect), _ws(client, project, "es_nope"):
        pass
    other = client.post(
        f"/organizations/{project['org']['id']}/projects",
        json={"name": "Other"},
        headers=project["headers"],
    ).json()["id"]
    key = client.post(
        f"/projects/{other}/ingest-keys", json={"name": "k"}, headers=project["headers"]
    ).json()["key"]
    with pytest.raises(WebSocketDisconnect), _ws(client, project, key):
        pass  # a valid key for another project is an outsider


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
        events, "_client", lambda: (_ for _ in ()).throw(ConnectionError("redis down"))
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

    committed = json.loads(Path("openapi.json").read_text())
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
