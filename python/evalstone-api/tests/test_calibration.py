import copy
import json
from pathlib import Path

import pytest
from evalstone.checks.human import output_hash
from evalstone.output import Output

from app.services import calibration as svc

REPORT = json.loads((Path(__file__).parent / "fixtures" / "rag-bot-ci-report.json").read_text())
JV = "8d4f2a1b9c0e7f33"


def _judged_report(run_id="judge0000001", jv=JV, model="local/tiny", flip: set[str] = frozenset()):
    """The sample report with one judge check `helpful` whose verdicts the humans will grade."""
    r = copy.deepcopy(REPORT)
    r["id"] = run_id
    r["check_keys"] = ["helpful"]
    seen = {}
    for res in r["results"]:
        seen.setdefault(res["sample_id"], res)
    results = []
    for sid, res in seen.items():
        passed = sid not in flip  # the judge says pass unless flipped
        results.append(
            {
                **res,
                "check_key": "helpful",
                "score": {
                    "value": 0.75 if passed else 0.25,
                    "passed": passed,
                    "reason": "4/5" if passed else "2/5",
                    "cost_usd": 0.0001,
                    "latency_ms": 10.0,
                    "error": None,
                    "skipped": False,
                    "raw": {
                        "model": model,
                        "score": 4 if passed else 2,
                        "scale": 5,
                        "judge_version": jv,
                    },
                },
            }
        )
    r["results"] = results
    r["summary"]["results"] = len(results)
    return r


def _label(client, project, res, *, passed, value=None, check=None):
    oh = output_hash(Output.model_validate(res["output"]))
    body = {
        "sample_id": res["sample_id"],
        "output_hash": oh,
        "value": value if value is not None else (1.0 if passed else 0.0),
        "passed": passed,
    }
    if check:
        body["check"] = check
    r = client.post(
        f"/projects/{project['id']}/labels", json={"labels": [body]}, headers=project["headers"]
    )
    assert r.status_code == 200, r.text


def test_kappa():
    assert svc.kappa(5, 0, 0, 5) == pytest.approx(1.0)  # perfect agreement
    assert svc.kappa(0, 5, 5, 0) == pytest.approx(-1.0)  # perfect disagreement
    assert svc.kappa(0, 0, 0, 0) is None
    assert svc.kappa(10, 0, 0, 0) is None  # no variation → undefined
    assert svc.kappa(3, 2, 2, 3) == pytest.approx(0.2)


def test_judges_lists_versions_seen_in_runs(client, project):
    h = project["headers"]
    assert client.get(f"/projects/{project['id']}/judges", headers=h).json() == []
    client.post(f"/projects/{project['id']}/runs", json=_judged_report(), headers=h)
    client.post(
        f"/projects/{project['id']}/runs",
        json=_judged_report(run_id="judge0000002", jv="aaaaaaaaaaaaaaaa", model="other/big"),
        headers=h,
    )
    client.post(f"/projects/{project['id']}/runs", json=REPORT, headers=h)  # deterministic only
    rows = client.get(f"/projects/{project['id']}/judges", headers=h).json()
    assert {
        (r["check_key"], r["judge_version"], r["model"], r["results"], r["runs"]) for r in rows
    } == {
        ("helpful", JV, "local/tiny", 10, 1),
        ("helpful", "aaaaaaaaaaaaaaaa", "other/big", 10, 1),
    }


def test_calibration_end_to_end_through_the_task(client, project):
    h = project["headers"]
    report = _judged_report(flip={"express", "refund-time"})  # the judge fails these two
    client.post(f"/projects/{project['id']}/runs", json=report, headers=h)
    by_id = {r["sample_id"]: r for r in report["results"]}
    # humans: 8 of the 10 samples labelled; refund-time → judge fail / human pass (fn);
    # warranty → judge pass / human fail (fp); express → both fail (tn); the rest both pass (tp)
    humans = {
        "return-window": True,
        "sale-return": True,
        "express": False,
        "refund-time": True,
        "warranty": False,
        "ship-to-uk": True,
        "shipping-time": True,
        "delete-account": True,
    }
    for sid, passed in humans.items():
        if sid in by_id:
            _label(client, project, by_id[sid], passed=passed)
    r = client.post(
        f"/projects/{project['id']}/calibrations", json={"check_key": "helpful"}, headers=h
    )
    assert r.status_code == 202, r.text
    cal = r.json()
    assert cal["judge_version"] == JV  # latest version picked
    row = client.get(f"/projects/{project['id']}/calibrations/{cal['id']}", headers=h).json()
    assert row["status"] == "done", row  # Celery is eager in tests
    labelled = [sid for sid in humans if sid in by_id]
    assert row["n"] == len(labelled) and row["model"] == "local/tiny"
    c = row["confusion"]
    assert c["fn"] == 1 and c["fp"] == 1 and c["tn"] == 1 and c["tp"] == row["n"] - 3
    assert row["agreement"] == pytest.approx((row["n"] - 2) / row["n"])
    assert row["kappa"] == pytest.approx(svc.kappa(c["tp"], c["fp"], c["fn"], c["tn"]))
    assert 0 < row["mean_abs_error"] < 1
    listed = client.get(
        f"/projects/{project['id']}/calibrations?check_key=helpful", headers=h
    ).json()
    assert [x["id"] for x in listed] == [cal["id"]]


def test_calibration_uses_the_latest_verdict_per_output_and_label_check(client, project):
    h = project["headers"]
    first = _judged_report(flip={"express"})
    client.post(f"/projects/{project['id']}/runs", json=first, headers=h)
    second = _judged_report(run_id="judge0000003")  # same version, now passes express
    client.post(f"/projects/{project['id']}/runs", json=second, headers=h)
    res = next(r for r in second["results"] if r["sample_id"] == "express")
    _label(client, project, res, passed=True, check="helpful")  # a label under the check's slot
    r = client.post(
        f"/projects/{project['id']}/calibrations",
        json={"check_key": "helpful", "judge_version": JV, "label_check": "helpful"},
        headers=h,
    ).json()
    assert (
        r["status"] == "done"
        and r["n"] == 1
        and r["confusion"] == {"tp": 1, "fp": 0, "fn": 0, "tn": 0}
    )
    assert r["kappa"] is None  # no variation in one pair
    overall = client.post(
        f"/projects/{project['id']}/calibrations", json={"check_key": "helpful"}, headers=h
    ).json()
    assert overall["status"] == "failed" and "no human labels" in overall["error"]


def test_failures_are_recorded_not_raised(client, project):
    h = project["headers"]
    r = client.post(
        f"/projects/{project['id']}/calibrations", json={"check_key": "nope"}, headers=h
    )
    assert r.status_code == 422 and "no judge verdicts" in r.json()["detail"]
    client.post(f"/projects/{project['id']}/runs", json=_judged_report(), headers=h)
    r = client.post(
        f"/projects/{project['id']}/calibrations",
        json={"check_key": "helpful", "judge_version": "0000000000000000"},
        headers=h,
    )
    assert (
        r.status_code == 202
        and r.json()["status"] == "failed"
        and "no human labels" in r.json()["error"]
    )


def test_roles_and_scope(client, project, register):
    h = project["headers"]
    stranger_h, _ = register("s@x.example.com")
    assert client.get(f"/projects/{project['id']}/judges", headers=stranger_h).status_code == 404
    secret = client.post(
        f"/projects/{project['id']}/ingest-keys", json={"name": "ci"}, headers=h
    ).json()["key"]
    assert (
        client.get(
            f"/projects/{project['id']}/judges", headers={"Authorization": f"Bearer {secret}"}
        ).status_code
        == 401
    )
