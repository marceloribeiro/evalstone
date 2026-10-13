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


# --- regressions from the #29 review ---------------------------------------------------------


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.__setitem__("id", "x" * 65),
        lambda r: r.__setitem__("trigger", "github-actions-nightly-and-then-some-more-text"),
        lambda r: r["results"][0].__setitem__("sample_id", "s" * 201),
    ],
)
def test_over_long_library_strings_are_422_not_500(client, project, mutate):
    report = _variant(REPORT, run_id="0a0a0a0a0a0a")
    mutate(report)
    r = _push(client, project, report)
    assert r.status_code == 422 and "longer than" in r.json()["detail"]


def test_two_baselines_per_suite_are_impossible_at_the_database(client, project, db):
    from sqlalchemy.exc import IntegrityError

    from app.models import Run

    a = _push(client, project, REPORT).json()["id"]
    b = _push(client, project, _variant(REPORT, run_id="1b1b1b1b1b1b")).json()["id"]
    import uuid

    db.get(Run, uuid.UUID(a)).is_baseline = True
    db.get(Run, uuid.UUID(b)).is_baseline = True
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_soft_deleted_run_frees_its_client_run_id(client, project, db):
    import uuid
    from datetime import UTC, datetime

    from app.models import Run

    first = _push(client, project, REPORT).json()["id"]
    db.get(Run, uuid.UUID(first)).deleted_at = datetime.now(UTC)
    db.commit()
    again = _push(client, project, REPORT)
    assert again.status_code == 201 and again.json()["id"] != first


def test_report_keeps_the_library_result_order(client, project):
    report = _variant(REPORT, run_id="2c2c2c2c2c2c")
    report["results"] = list(reversed(report["results"]))
    rid = _push(client, project, report).json()["id"]
    out = client.get(
        f"/projects/{project['id']}/runs/{rid}/report", headers=project["headers"]
    ).json()
    assert [(r["sample_id"], r["check_key"]) for r in out["results"]] == [
        (r["sample_id"], r["check_key"]) for r in report["results"]
    ]


def test_concurrent_pushes_of_one_report_serialise(client, project, db):
    from concurrent.futures import ThreadPoolExecutor

    from app.models import Run

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _: _push(client, project, REPORT).status_code, range(2)))
    assert statuses == [200, 201], statuses
    assert db.query(Run).count() == 1 and db.query(RunResult).count() == 40


def test_oversized_result_is_422(client, project):
    report = _variant(REPORT, run_id="3d3d3d3d3d3d")
    report["results"][0]["output"]["value"] = "x" * (svc.MAX_RESULT_BYTES + 1)
    r = _push(client, project, report)
    assert r.status_code == 422 and "bytes" in r.json()["detail"]


def test_summary_is_recomputed_from_the_rows(client, project):
    report = _variant(REPORT, run_id="4e4e4e4e4e4e")
    report["summary"]["pass_rate"] = 1.0  # a lying client
    report["summary"]["results"] = 999
    run = _push(client, project, report).json()
    assert run["pass_rate"] == pytest.approx(0.875) and run["summary"]["results"] == 40
    assert (
        run["summary"]["duration_ms"] == report["summary"]["duration_ms"]
    )  # only the client knows


def test_dataset_link_prefers_the_named_live_dataset(client, project):
    h, pid = project["headers"], project["id"]
    samples = [{"input": "x", "expected": "y"}]
    ids = {}
    for name in ("other", "golden"):
        did = client.post(f"/projects/{pid}/datasets", json={"name": name}, headers=h).json()["id"]
        ids[name] = client.post(
            f"/projects/{pid}/datasets/{did}/versions", json={"samples": samples}, headers=h
        ).json()
        ids[name]["dataset_id"] = did
    report = _variant(REPORT, run_id="5f5f5f5f5f5f")
    report["dataset"], report["dataset_hash"] = "golden", ids["golden"]["content_hash"]
    assert _push(client, project, report).json()["dataset_version_id"] == ids["golden"]["id"]
    client.delete(f"/projects/{pid}/datasets/{ids['golden']['dataset_id']}", headers=h)
    report["id"] = "6a6a6a6a6a6a"
    assert _push(client, project, report).json()["dataset_version_id"] == ids["other"]["id"]


def test_history_paging_is_stable_on_started_at_ties(client, project):
    h, pid = project["headers"], project["id"]
    ids = {
        _push(client, project, _variant(REPORT, run_id=f"7{i}" * 6)).json()["id"] for i in range(3)
    }
    seen = [
        client.get(f"/projects/{pid}/runs?limit=1&offset={o}", headers=h).json()["items"][0]["id"]
        for o in range(3)
    ]
    assert set(seen) == ids and len(set(seen)) == 3


def test_no_unused_baseline_helper():
    assert not hasattr(svc, "current_baseline")
