import copy
import json
from pathlib import Path

import pytest
from evalstone.run import Run as LibRun
from evalstone.run import compare as lib_compare

from app.models import RunResult
from app.services import runs as svc

REPORT = json.loads((Path(__file__).parent / "fixtures" / "rag-bot-ci-report.json").read_text())


def _push(client, project, report, headers=None):
    return client.post(
        f"/projects/{project['id']}/runs", json=report, headers=headers or project["headers"]
    )


def _variant(report, *, run_id, flip_sample=None, sha="deadbeef"):
    """A second run: same shape, a different id and (optionally) one result flipped."""
    r = copy.deepcopy(report)
    r["id"], r["git_sha"] = run_id, sha
    if flip_sample:
        for res in r["results"]:
            if res["sample_id"] == flip_sample[0] and res["check_key"] == flip_sample[1]:
                res["score"]["passed"] = not res["score"]["passed"]
                res["score"]["value"] = 1.0 if res["score"]["passed"] else 0.0
                res["score"]["reason"] = "flipped by the test"
        passed = sum(1 for x in r["results"] if x["score"]["passed"])
        r["summary"]["passed"] = passed
        r["summary"]["pass_rate"] = passed / len(r["results"])
    return r


def test_push_stores_the_library_report_and_is_idempotent(client, project, db):
    r = _push(client, project, REPORT)
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["client_run_id"] == REPORT["id"] and run["suite"] == "ci"
    assert run["result_count"] == 40 and run["pass_rate"] == pytest.approx(0.875)
    assert run["summary"]["per_check"][0]["key"] == "must_include"
    assert run["dataset_version_id"] is None  # the center has no version with that hash yet
    again = _push(client, project, REPORT)
    assert again.status_code == 200 and again.json()["id"] == run["id"]
    assert db.query(RunResult).count() == 40
    page = client.get(f"/projects/{project['id']}/runs", headers=project["headers"]).json()
    assert page["total"] == 1 and page["items"][0]["id"] == run["id"]


def test_results_filter_and_page(client, project):
    rid = _push(client, project, REPORT).json()["id"]
    url = f"/projects/{project['id']}/runs/{rid}/results"
    failed = client.get(url + "?failed_only=true", headers=project["headers"]).json()
    assert failed["total"] == 5 and all(not x["passed"] for x in failed["items"])
    one = client.get(url + "?check_key=must_include&limit=3", headers=project["headers"]).json()
    assert one["total"] == 10 and len(one["items"]) == 3
    assert one["items"][0]["output"]["value"] and "input" in one["items"][0]


def test_report_round_trips_through_the_library_model(client, project, db):
    rid = _push(client, project, REPORT).json()["id"]
    out = client.get(
        f"/projects/{project['id']}/runs/{rid}/report", headers=project["headers"]
    ).json()
    rebuilt = LibRun.model_validate(out)
    original = LibRun.model_validate(REPORT)
    assert rebuilt.id == original.id and rebuilt.summary == original.summary
    assert {(r.sample_id, r.check_key): r.score for r in rebuilt.results} == {
        (r.sample_id, r.check_key): r.score for r in original.results
    }


def test_compare_matches_the_library(client, project):
    a = _push(client, project, REPORT).json()["id"]
    flipped = _variant(REPORT, run_id="bbbbbbbbbbbb", flip_sample=("return-window", "must_include"))
    b = _push(client, project, flipped).json()["id"]
    out = client.get(
        f"/projects/{project['id']}/runs/{a}/compare/{b}", headers=project["headers"]
    ).json()
    expected = lib_compare(LibRun.model_validate(REPORT), LibRun.model_validate(flipped))
    assert out["regressions"] == [f.model_dump(mode="json") for f in expected.regressions]
    assert out["pass_rate_delta"] == pytest.approx(expected.pass_rate_delta)
    assert out["same_dataset"] is True and len(out["regressions"]) == 1


def test_baseline_is_one_per_suite_and_links_on_push(client, project):
    h = project["headers"]
    a = _push(client, project, REPORT).json()["id"]
    r = client.put(f"/projects/{project['id']}/runs/{a}/baseline", json={}, headers=h)
    assert r.status_code == 200 and r.json()["is_baseline"] is True
    second = _variant(REPORT, run_id="cccccccccccc")
    second["baseline_run_id"] = REPORT["id"]  # the library records the baseline it compared to
    b = _push(client, project, second).json()
    assert b["baseline_run_id"] == a and b["client_baseline_run_id"] == REPORT["id"]
    client.put(f"/projects/{project['id']}/runs/{b['id']}/baseline", json={}, headers=h)
    baselines = client.get(f"/projects/{project['id']}/runs?baseline=true", headers=h).json()
    assert [x["id"] for x in baselines["items"]] == [b["id"]]  # the previous one was unmarked
    other_suite = _variant(REPORT, run_id="dddddddddddd")
    other_suite["suite"] = "nightly"
    c = _push(client, project, other_suite).json()["id"]
    client.put(f"/projects/{project['id']}/runs/{c}/baseline", json={}, headers=h)
    assert (
        client.get(f"/projects/{project['id']}/runs?baseline=true", headers=h).json()["total"] == 2
    )
    off = client.put(
        f"/projects/{project['id']}/runs/{c}/baseline", json={"is_baseline": False}, headers=h
    )
    assert off.json()["is_baseline"] is False


def test_run_links_a_dataset_version_by_content_hash(client, project):
    h = project["headers"]
    did = client.post(
        f"/projects/{project['id']}/datasets", json={"name": "golden"}, headers=h
    ).json()["id"]
    v = client.post(
        f"/projects/{project['id']}/datasets/{did}/versions",
        json={"samples": [{"input": "x", "expected": "y"}]},
        headers=h,
    ).json()
    report = _variant(REPORT, run_id="eeeeeeeeeeee")
    report["dataset_hash"] = v["content_hash"]
    run = _push(client, project, report).json()
    assert run["dataset_version_id"] == v["id"]


def test_push_validation_and_actors(client, project, register):
    bad = _push(client, project, {"id": "x", "suite": "ci"})
    assert bad.status_code == 422 and "invalid run report" in bad.json()["detail"]
    dup = copy.deepcopy(REPORT)
    dup["id"] = "ffffffffffff"
    dup["results"].append(copy.deepcopy(dup["results"][0]))
    assert "duplicate result" in _push(client, project, dup).json()["detail"]
    secret = client.post(
        f"/projects/{project['id']}/ingest-keys", json={"name": "ci"}, headers=project["headers"]
    ).json()["key"]
    kh = {"Authorization": f"Bearer {secret}"}
    r = _push(client, project, _variant(REPORT, run_id="a1a1a1a1a1a1"), headers=kh)
    assert r.status_code == 201 and r.json()["created_by_user_id"] is None
    assert (
        client.put(
            f"/projects/{project['id']}/runs/{r.json()['id']}/baseline", json={}, headers=kh
        ).status_code
        == 401
    )
    stranger_h, _ = register("s@x.example.com")
    assert client.get(f"/projects/{project['id']}/runs", headers=stranger_h).status_code == 404


def test_cap_on_results(client, project):
    big = _variant(REPORT, run_id="b1b1b1b1b1b1")
    base = big["results"][0]
    big["results"] = [
        {**copy.deepcopy(base), "sample_id": f"s{i}"} for i in range(svc.MAX_RESULTS_PER_RUN + 1)
    ]
    assert _push(client, project, big).status_code == 422
