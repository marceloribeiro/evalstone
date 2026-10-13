import copy
import json
from pathlib import Path

import pytest
from evalstone.checks.human import LabelStore, output_hash
from evalstone.output import Output

from app.services import label_queues as svc

REPORT = json.loads((Path(__file__).parent / "fixtures" / "rag-bot-ci-report.json").read_text())


def _push(client, project, report):
    r = client.post(f"/projects/{project['id']}/runs", json=report, headers=project["headers"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _q(project, suffix=""):
    return f"/projects/{project['id']}/label-queues" + suffix


@pytest.fixture
def run(client, project):
    return _push(client, project, REPORT)


def test_grade_queue_one_task_per_sample_and_answers_become_labels(client, project, run, db):
    h = project["headers"]
    r = client.post(
        _q(project),
        json={
            "name": "grade ci",
            "kind": "grade",
            "source": {"run_id": run, "failed_only": True},
            "scale": 5,
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    queue = r.json()
    assert queue["task_count"] == 5  # 5 failed results, 5 distinct samples
    qid = queue["id"]
    progress = client.get(_q(project, f"/{qid}/progress"), headers=h).json()
    assert progress == {"total": 5, "pending": 5, "claimed": 0, "done": 0, "skipped": 0}
    task = client.post(_q(project, f"/{qid}/next"), headers=h).json()
    assert task["status"] == "pending" and task["assignee_user_id"] == project["org"]["user"]["id"]
    assert task["payload"]["machine"]["passed"] is False and "input" in task["payload"]
    expected_hash = output_hash(Output.model_validate(task["payload"]["output"]))
    assert task["output_hash"] == expected_hash
    done = client.post(
        _q(project, f"/{qid}/tasks/{task['id']}/answer"),
        json={"grade": 4, "notes": "fine"},
        headers=h,
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "done" and done.json()["label_id"]
    label = client.get(
        f"/projects/{project['id']}/labels/lookup",
        params={"sample_key": task["sample_key"], "output_hash": task["output_hash"]},
        headers=h,
    ).json()
    assert label["value"] == 0.75 and label["passed"] is True and label["raw"]["grade"] == 4
    assert label["notes"] == "fine" and label["labeler"] == "owner@acme.example.com"
    assert client.get(_q(project, f"/{qid}/progress"), headers=h).json()["done"] == 1
    again = client.post(
        _q(project, f"/{qid}/tasks/{task['id']}/answer"), json={"grade": 1}, headers=h
    )
    assert again.status_code == 409


def test_grade_scale_two_and_pass_rules(client, project, run):
    h = project["headers"]
    qid = client.post(
        _q(project),
        json={"name": "pf", "kind": "grade", "source": {"run_id": run}, "scale": 2},
        headers=h,
    ).json()["id"]
    t = client.post(_q(project, f"/{qid}/next"), headers=h).json()
    r = client.post(
        _q(project, f"/{qid}/tasks/{t['id']}/answer"), json={"grade": 2}, headers=h
    ).json()
    assert r["status"] == "done"
    label = client.get(
        f"/projects/{project['id']}/labels/lookup",
        params={"sample_key": t["sample_key"], "output_hash": t["output_hash"]},
        headers=h,
    ).json()
    assert label["value"] == 1.0 and label["passed"] is True  # top level passes on a 2-point scale
    t2 = client.post(_q(project, f"/{qid}/next"), headers=h).json()
    bad = client.post(_q(project, f"/{qid}/tasks/{t2['id']}/answer"), json={"grade": 3}, headers=h)
    assert bad.status_code == 422
    pf = client.post(
        _q(project, f"/{qid}/tasks/{t2['id']}/answer"), json={"passed": False}, headers=h
    )
    assert pf.status_code == 200
    none = client.post(_q(project, f"/{qid}/tasks/{t2['id']}/answer"), json={}, headers=h)
    assert none.status_code == 409  # already done


def test_compare_queue_records_the_winner(client, project, run):
    h = project["headers"]
    other = copy.deepcopy(REPORT)
    other["id"] = "bbbbbbbbbbbb"
    for res in other["results"]:
        res["output"]["value"] = res["output"]["value"] + " (v2)"
    run_b = _push(client, project, other)
    r = client.post(
        _q(project),
        json={"name": "a vs b", "kind": "compare", "source": {"run_a": run, "run_b": run_b}},
        headers=h,
    )
    assert r.status_code == 201, r.text
    qid = r.json()["id"]
    assert r.json()["task_count"] == 10  # one per shared sample
    t = client.post(_q(project, f"/{qid}/next"), headers=h).json()
    assert t["payload"]["a"]["hash"] != t["payload"]["b"]["hash"]
    no_winner = client.post(
        _q(project, f"/{qid}/tasks/{t['id']}/answer"), json={"grade": 3}, headers=h
    )
    assert no_winner.status_code == 422
    done = client.post(
        _q(project, f"/{qid}/tasks/{t['id']}/answer"), json={"winner": "b"}, headers=h
    ).json()
    label = client.get(
        f"/projects/{project['id']}/labels/lookup",
        params={"sample_key": t["sample_key"], "output_hash": t["output_hash"]},
        headers=h,
    ).json()
    assert label["value"] == 0.0 and label["raw"]["comparison"]["winner"] == "b"
    assert done["label_id"] == label["id"]
    same = client.post(
        _q(project),
        json={"name": "x", "kind": "compare", "source": {"run_a": run, "run_b": run}},
        headers=h,
    )
    assert same.status_code == 422


def test_verify_queue_from_a_dataset_version(client, project):
    h = project["headers"]
    did = client.post(
        f"/projects/{project['id']}/datasets", json={"name": "golden"}, headers=h
    ).json()["id"]
    v = client.post(
        f"/projects/{project['id']}/datasets/{did}/versions",
        json={
            "samples": [
                {"input": "2+2", "expected": "4"},
                {"input": "capital", "expected": "Paris"},
            ]
        },
        headers=h,
    ).json()
    r = client.post(
        _q(project),
        json={
            "name": "verify",
            "kind": "verify",
            "source": {"dataset_id": did, "version": v["version"]},
            "scale": 2,
        },
        headers=h,
    )
    assert r.status_code == 201 and r.json()["task_count"] == 2
    t = client.post(_q(project, f"/{r.json()['id']}/next"), headers=h).json()
    assert t["payload"]["expected"] in ("4", "Paris")
    assert t["output_hash"] == output_hash(Output(value=t["payload"]["expected"]))
    missing = client.post(
        _q(project),
        json={"name": "x", "kind": "verify", "source": {"dataset_id": did, "version": 9}},
        headers=h,
    )
    assert missing.status_code == 404


def test_assignment_round_robin_and_mine_first(client, project, run, register):
    h = project["headers"]
    emails = ["a@acme.example.com", "b@acme.example.com"]
    headers = {}
    for e in emails:
        headers[e], _ = register(e)
        client.post(
            f"/organizations/{project['org']['id']}/invitations", json={"email": e}, headers=h
        )
    members = client.get(f"/organizations/{project['org']['id']}/members", headers=h).json()
    ids = {m["user"]["email"]: m["user"]["id"] for m in members}
    qid = client.post(
        _q(project), json={"name": "g", "kind": "grade", "source": {"run_id": run}}, headers=h
    ).json()["id"]
    r = client.post(
        _q(project, f"/{qid}/assign"), json={"user_ids": [ids[e] for e in emails]}, headers=h
    )
    assert r.json() == {"assigned": 10}
    a_tasks = client.get(
        _q(project, f"/{qid}/tasks"), params={"assignee": "me"}, headers=headers[emails[0]]
    ).json()
    b_tasks = client.get(
        _q(project, f"/{qid}/tasks"), params={"assignee": ids[emails[1]]}, headers=h
    ).json()
    assert a_tasks["total"] == 5 and b_tasks["total"] == 5
    assert [t["position"] for t in a_tasks["items"]] == [0, 2, 4, 6, 8]
    mine = client.post(_q(project, f"/{qid}/next"), headers=headers[emails[0]]).json()
    assert mine["assignee_user_id"] == ids[emails[0]] and mine["position"] == 0
    # b cannot answer a's task
    r = client.post(
        _q(project, f"/{qid}/tasks/{mine['id']}/answer"),
        json={"grade": 5},
        headers=headers[emails[1]],
    )
    assert r.status_code == 409
    # the owner, unassigned, gets nothing to claim
    assert client.post(_q(project, f"/{qid}/next"), headers=h).json() is None
    assert (
        client.post(
            _q(project, f"/{qid}/assign"),
            json={"user_ids": [ids[emails[0]]]},
            headers=headers[emails[0]],
        ).status_code
        == 403
    )


def test_concurrent_claims_never_hand_out_the_same_task(client, project, run, register):
    from concurrent.futures import ThreadPoolExecutor

    h = project["headers"]
    labelers = []
    for i in range(4):
        hd, _ = register(f"l{i}@acme.example.com")
        client.post(
            f"/organizations/{project['org']['id']}/invitations",
            json={"email": f"l{i}@acme.example.com"},
            headers=h,
        )
        labelers.append(hd)
    qid = client.post(
        _q(project), json={"name": "g", "kind": "grade", "source": {"run_id": run}}, headers=h
    ).json()["id"]

    def claim(hd):
        return client.post(_q(project, f"/{qid}/next"), headers=hd).json()["id"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(claim, labelers * 2))  # 8 claims by 4 people
    assert len(set(ids)) == 4  # each person got exactly one distinct task, re-asking returns theirs
    assert client.get(_q(project, f"/{qid}/progress"), headers=h).json()["claimed"] == 4


def test_skip_close_and_roles(client, project, run, register):
    h = project["headers"]
    qid = client.post(
        _q(project), json={"name": "g", "kind": "grade", "source": {"run_id": run}}, headers=h
    ).json()["id"]
    t = client.post(_q(project, f"/{qid}/next"), headers=h).json()
    s = client.post(
        _q(project, f"/{qid}/tasks/{t['id']}/skip"), json={"reason": "ambiguous"}, headers=h
    ).json()
    assert s["status"] == "skipped" and s["payload"]["skip_reason"] == "ambiguous"
    assert client.get(_q(project, f"/{qid}/progress"), headers=h).json()["skipped"] == 1
    assert (
        client.patch(_q(project, f"/{qid}"), json={"status": "closed"}, headers=h).json()["status"]
        == "closed"
    )
    assert client.post(_q(project, f"/{qid}/next"), headers=h).status_code == 409
    member_h, _ = register("m@acme.example.com")
    client.post(
        f"/organizations/{project['org']['id']}/invitations",
        json={"email": "m@acme.example.com"},
        headers=h,
    )
    assert (
        client.post(
            _q(project),
            json={"name": "x", "kind": "grade", "source": {"run_id": run}},
            headers=member_h,
        ).status_code
        == 403
    )
    assert client.get(_q(project), headers=member_h).status_code == 200
    stranger_h, _ = register("s@x.example.com")
    assert client.get(_q(project), headers=stranger_h).status_code == 404


def test_labels_from_a_queue_export_to_the_library(client, project, run, tmp_path):
    h = project["headers"]
    qid = client.post(
        _q(project),
        json={"name": "g", "kind": "grade", "source": {"run_id": run}, "check_key": "helpful"},
        headers=h,
    ).json()["id"]
    t = client.post(_q(project, f"/{qid}/next"), headers=h).json()
    client.post(_q(project, f"/{qid}/tasks/{t['id']}/answer"), json={"grade": 5}, headers=h)
    jsonl = client.get(f"/projects/{project['id']}/labels/export", headers=h).text
    path = tmp_path / "labels.jsonl"
    path.write_text(jsonl)
    store = LabelStore(path)
    label = store.get(
        t["sample_key"], Output.model_validate(t["payload"]["output"]), check="helpful"
    )
    assert label is not None and label.value == 1.0 and label.raw["queue_id"] == qid


def test_bad_sources(client, project, run):
    h = project["headers"]
    assert (
        client.post(
            _q(project), json={"name": "x", "kind": "grade", "source": {}}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.post(
            _q(project),
            json={"name": "x", "kind": "grade", "source": {"run_id": "nope"}},
            headers=h,
        ).status_code
        == 422
    )
    empty = client.post(
        _q(project),
        json={"name": "x", "kind": "grade", "source": {"run_id": run, "check_key": "nope"}},
        headers=h,
    )
    assert empty.status_code == 422 and "no tasks" in empty.json()["detail"]
    assert svc.MAX_TASKS_PER_QUEUE == 5000
