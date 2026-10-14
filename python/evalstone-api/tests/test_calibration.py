import copy
import json
from pathlib import Path

import pytest
from evalstone.checks.human import output_hash
from evalstone.output import Output

from app.services import calibration as svc

REPORT = json.loads((Path(__file__).parent / "fixtures" / "rag-bot-ci-report.json").read_text())
JV = "8d4f2a1b9c0e7f33"


def _judged_report(
    run_id="judge0000001",
    jv=JV,
    model="local/tiny",
    flip: set[str] = frozenset(),
    judge_model: str | None = None,
):
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
                        **({"judge_model": judge_model} if judge_model else {}),
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


# --- regressions from the #36 review ---------------------------------------------------------


def test_ingest_stamps_output_hash_and_judge_version(client, project, db):
    from app.models import RunResult
    from app.services import label_queues as lq
    from app.services.runs import output_hash_of

    h = project["headers"]
    client.post(f"/projects/{project['id']}/runs", json=_judged_report(), headers=h)
    rows = db.query(RunResult).all()
    assert all(r.output_hash == output_hash_of(r.output) for r in rows)
    assert {r.judge_version for r in rows} == {JV} and {r.judge_model for r in rows} == {
        "local/tiny"
    }
    assert lq._hash_of is output_hash_of  # one hashing rule for tasks and calibration


def test_latest_verdict_is_by_run_finish_time_not_ingest_order(client, project):
    """A backfilled OLDER run pushed later must not override the newer verdict."""
    h = project["headers"]
    newer = _judged_report(run_id="judge00newer")  # express passes
    older = _judged_report(run_id="judge00older", flip={"express"})  # express failed, earlier
    older["started_at"], older["finished_at"] = "2026-10-01T00:00:00Z", "2026-10-01T00:00:01Z"
    client.post(f"/projects/{project['id']}/runs", json=newer, headers=h)
    client.post(f"/projects/{project['id']}/runs", json=older, headers=h)  # ingested last
    res = next(r for r in newer["results"] if r["sample_id"] == "express")
    _label(client, project, res, passed=True)
    r = client.post(
        f"/projects/{project['id']}/calibrations", json={"check_key": "helpful"}, headers=h
    ).json()
    assert r["status"] == "done" and r["confusion"] == {"tp": 1, "fp": 0, "fn": 0, "tn": 0}


def test_errored_and_skipped_verdicts_are_not_verdicts(client, project):
    h = project["headers"]
    report = _judged_report()
    res = next(r for r in report["results"] if r["sample_id"] == "express")
    res["score"].update({"error": "judge: provider down", "passed": False, "value": 0.0})
    client.post(f"/projects/{project['id']}/runs", json=report, headers=h)
    _label(client, project, res, passed=True)
    r = client.post(
        f"/projects/{project['id']}/calibrations", json={"check_key": "helpful"}, headers=h
    ).json()
    assert (
        r["status"] == "failed" and "no overlap" in r["error"]
    )  # the only labelled verdict errored


def test_db_error_inside_compute_is_recorded_not_stuck_running(client, project, db, monkeypatch):
    import uuid

    from sqlalchemy import text

    from app.models import Calibration
    from app.services import calibration as cal

    h = project["headers"]
    client.post(f"/projects/{project['id']}/runs", json=_judged_report(), headers=h)
    real = cal.compute

    def poisoned(db_, *a, **k):
        db_.execute(text("SELECT * FROM no_such_table"))  # aborts the PG transaction
        return real(db_, *a, **k)

    monkeypatch.setattr(cal, "compute", poisoned)
    r = client.post(
        f"/projects/{project['id']}/calibrations", json={"check_key": "helpful"}, headers=h
    ).json()
    assert r["status"] == "failed" and "no_such_table" in r["error"]
    assert db.get(Calibration, uuid.UUID(r["id"])).status == "failed"


def test_broker_failure_marks_the_row_failed(client, project, monkeypatch):
    from app import tasks

    h = project["headers"]
    client.post(f"/projects/{project['id']}/runs", json=_judged_report(), headers=h)

    def boom(*a, **k):
        raise ConnectionError("redis down")

    monkeypatch.setattr(tasks.calibrate, "delay", boom)
    r = client.post(
        f"/projects/{project['id']}/calibrations", json={"check_key": "helpful"}, headers=h
    )
    assert r.status_code == 202 and r.json()["status"] == "failed"
    assert "could not enqueue" in r.json()["error"] and "redis down" in r.json()["error"]


def test_too_many_labels_fails_loudly(client, project, monkeypatch):
    from app.services import calibration as cal

    h = project["headers"]
    report = _judged_report()
    client.post(f"/projects/{project['id']}/runs", json=report, headers=h)
    for res in report["results"][:3]:
        _label(client, project, res, passed=True)
    monkeypatch.setattr(cal, "MAX_PAIRS", 2)
    r = client.post(
        f"/projects/{project['id']}/calibrations", json={"check_key": "helpful"}, headers=h
    ).json()
    assert r["status"] == "failed" and "the limit is 2" in r["error"]


def test_latest_version_is_per_check_and_by_finish_time(client, project, db):
    from uuid import UUID

    from app.services import calibration as cal
    from app.services import projects as project_svc

    h = project["headers"]
    a = _judged_report(run_id="judge0000000a", jv="aaaaaaaaaaaaaaaa")
    b = _judged_report(run_id="judge0000000b", jv="bbbbbbbbbbbbbbbb")
    b["started_at"], b["finished_at"] = "2026-10-01T00:00:00Z", "2026-10-01T00:00:01Z"  # older
    client.post(f"/projects/{project['id']}/runs", json=b, headers=h)
    client.post(f"/projects/{project['id']}/runs", json=a, headers=h)
    p = project_svc.get_project(db, UUID(project["id"]))
    assert cal.latest_version(db, p, "helpful") == "aaaaaaaaaaaaaaaa"
    assert cal.latest_version(db, p, "other") is None


def test_promote_pins_the_routed_model_not_the_provider_reported_one(client, project):
    """Regression (first real-vendor run): OpenRouter reports `anthropic/claude-haiku-5.5`, but
    the verdict was routed through `openrouter/…`. Promote PUTs the calibration's `model` into the
    judge settings, which only accept `<org provider>/<model>` — so it must be the routed one."""
    h, org = project["headers"], project["org"]
    r = client.post(
        f"/organizations/{org['id']}/providers",
        json={
            "name": "openrouter",
            "adapter": "openai",
            "base_url": "https://openrouter.ai/api/v1",
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    report = _judged_report(
        model="anthropic/claude-haiku-5.5", judge_model="openrouter/anthropic/claude-haiku-5.5"
    )
    client.post(f"/projects/{project['id']}/runs", json=report, headers=h)
    for res in report["results"]:
        _label(client, project, res, passed=True)
    judges = client.get(f"/projects/{project['id']}/judges", headers=h).json()
    assert [j["model"] for j in judges] == ["openrouter/anthropic/claude-haiku-5.5"]
    cal = client.post(
        f"/projects/{project['id']}/calibrations", json={"check_key": "helpful"}, headers=h
    ).json()
    row = client.get(f"/projects/{project['id']}/calibrations/{cal['id']}", headers=h).json()
    assert row["model"] == "openrouter/anthropic/claude-haiku-5.5"
    # what the web's Promote button sends
    put = client.put(
        f"/projects/{project['id']}/judge-settings",
        json={"default_model": None, "overrides": {"helpful": row["model"]}},
        headers=h,
    )
    assert put.status_code == 200, put.text
    assert put.json()["overrides"] == {"helpful": "openrouter/anthropic/claude-haiku-5.5"}


def test_the_newest_stamp_wins_when_libraries_mix_on_one_version(client, project):
    """One judge version pushed first by lib 0.2.2 (provider id only), then by 0.2.3 (routed):
    `min()` picked `anthropic/…` over `openrouter/…`; the newest verdict's stamp must win."""
    h = project["headers"]
    old = _judged_report(run_id="judge0000old", model="anthropic/claude-haiku-5.5")
    old["started_at"], old["finished_at"] = "2026-10-01T00:00:00Z", "2026-10-01T00:00:01Z"
    new = _judged_report(
        run_id="judge0000new",
        model="anthropic/claude-haiku-5.5",
        judge_model="openrouter/anthropic/claude-haiku-5.5",
    )
    client.post(f"/projects/{project['id']}/runs", json=new, headers=h)
    client.post(f"/projects/{project['id']}/runs", json=old, headers=h)  # ingested last
    judges = client.get(f"/projects/{project['id']}/judges", headers=h).json()
    assert [j["model"] for j in judges] == ["openrouter/anthropic/claude-haiku-5.5"]
    for res in new["results"]:
        _label(client, project, res, passed=True)
    cal = client.post(
        f"/projects/{project['id']}/calibrations", json={"check_key": "helpful"}, headers=h
    ).json()
    assert cal["status"] == "done" and cal["model"] == "openrouter/anthropic/claude-haiku-5.5"
