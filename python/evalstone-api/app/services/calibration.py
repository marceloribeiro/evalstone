"""Judge calibration: a judge version against the humans, on what both have graded.

`judges()` lists the judge versions seen in the project's run results (the library stamps
`raw.judge_version`, `raw.model` on every judge verdict). `compute()` joins those results
with the labels of the same (sample, output hash) and reports agreement, Cohen's kappa, a
pass/fail confusion matrix and the mean absolute error of the 0..1 values. The join runs in
a Celery task (`app.tasks.calibrate`) so a large project never blocks a request.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from evalstone.checks.human import output_hash
from evalstone.output import Output
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import Invalid, NotFound
from app.models import Calibration, Label, Project, Run, RunResult, User

MAX_RESULTS_SCANNED = 50_000
_JV = RunResult.raw["judge_version"].astext
_MODEL = RunResult.raw["model"].astext


def judges(db: Session, project: Project) -> list[dict[str, Any]]:
    """Every (check_key, judge_version) with its model, result and run counts and when seen."""
    rows = db.execute(
        select(
            RunResult.check_key,
            _JV,
            func.max(_MODEL),
            func.count(),
            func.count(func.distinct(RunResult.run_id)),
            func.min(RunResult.created_at),
            func.max(RunResult.created_at),
        )
        .join(Run, Run.id == RunResult.run_id)
        .where(Run.project_id == project.id, Run.deleted_at.is_(None), _JV.is_not(None))
        .group_by(RunResult.check_key, _JV)
        .order_by(RunResult.check_key, func.max(RunResult.created_at).desc())
    ).all()
    return [
        {
            "check_key": r[0],
            "judge_version": r[1],
            "model": r[2],
            "results": r[3],
            "runs": r[4],
            "first_seen": r[5],
            "last_seen": r[6],
        }
        for r in rows
    ]


def kappa(tp: int, fp: int, fn: int, tn: int) -> float | None:
    """Cohen's kappa for two binary raters; None when undefined (no variation)."""
    n = tp + fp + fn + tn
    if n == 0:
        return None
    po = (tp + tn) / n
    judge_pass = (tp + fp) / n
    human_pass = (tp + fn) / n
    pe = judge_pass * human_pass + (1 - judge_pass) * (1 - human_pass)
    if pe == 1.0:
        return None
    return (po - pe) / (1 - pe)


def compute(
    db: Session, project: Project, *, check_key: str, judge_version: str, label_check: str
) -> dict[str, Any]:
    labels = {
        (lb.sample_key, lb.output_hash): lb
        for lb in db.scalars(
            select(Label).where(
                Label.project_id == project.id,
                Label.check_key == label_check,
                Label.deleted_at.is_(None),
            )
        )
    }
    if not labels:
        raise Invalid(f"no human labels under check {label_check!r} in this project")
    results = db.scalars(
        select(RunResult)
        .join(Run, Run.id == RunResult.run_id)
        .where(
            Run.project_id == project.id,
            Run.deleted_at.is_(None),
            RunResult.check_key == check_key,
            judge_version == _JV,
            RunResult.sample_key.in_([k for k, _ in labels]),
        )
        .order_by(RunResult.created_at.desc())
        .limit(MAX_RESULTS_SCANNED)
    )
    tp = fp = fn = tn = 0
    abs_err = 0.0
    model = None
    seen: set[tuple[str, str]] = set()  # the latest verdict per (sample, output) counts once
    for r in results:
        key = (r.sample_key, output_hash(Output.model_validate(r.output)))
        lb = labels.get(key)
        if lb is None or key in seen:
            continue
        seen.add(key)
        model = model or (r.raw or {}).get("model")
        if r.passed and lb.passed:
            tp += 1
        elif r.passed and not lb.passed:
            fp += 1
        elif not r.passed and lb.passed:
            fn += 1
        else:
            tn += 1
        abs_err += abs(r.score - lb.value)
    n = tp + fp + fn + tn
    if n == 0:
        raise Invalid(
            f"no overlap: none of the {len(labels)} labelled outputs has a verdict from "
            f"{check_key}@{judge_version}"
        )
    return {
        "n": n,
        "agreement": (tp + tn) / n,
        "kappa": kappa(tp, fp, fn, tn),
        "mean_abs_error": abs_err / n,
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "model": model,
    }


# --- rows + job -------------------------------------------------------------------------------


def request(
    db: Session,
    *,
    project: Project,
    check_key: str,
    judge_version: str | None,
    label_check: str,
    created_by: User | None,
) -> Calibration:
    """Queue a calibration (the latest judge version of the check when none is given)."""
    if judge_version is None:
        latest = next((j for j in judges(db, project) if j["check_key"] == check_key), None)
        if latest is None:
            raise Invalid(f"no judge verdicts for check {check_key!r} in this project")
        judge_version = latest["judge_version"]
    row = Calibration(
        project_id=project.id,
        check_key=check_key,
        judge_version=judge_version,
        label_check=label_check,
        created_by_user_id=created_by.id if created_by else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    from app.tasks import calibrate  # the task module imports this one

    calibrate.delay(str(row.id))
    db.refresh(row)  # an eager (tests) or very fast worker may already have finished it
    return row


def run_job(db: Session, calibration_id: uuid.UUID) -> Calibration:
    """The Celery body: compute and store, or record the failure. Idempotent on a done row."""
    row = db.get(Calibration, calibration_id)
    if row is None:
        raise NotFound("calibration not found")
    if row.status == "done":
        return row
    row.status, row.started_at = "running", datetime.now(UTC)
    db.commit()
    project = db.get(Project, row.project_id)
    try:
        stats = compute(
            db,
            project,
            check_key=row.check_key,
            judge_version=row.judge_version,
            label_check=row.label_check,
        )
    except Exception as exc:
        row.status, row.error = "failed", f"{type(exc).__name__}: {str(exc)[:900]}"
        row.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        return row
    for k, v in stats.items():
        setattr(row, k, v)
    row.status, row.finished_at = "done", datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return row


def list_calibrations(
    db: Session, project: Project, *, check_key: str | None = None
) -> list[Calibration]:
    q = select(Calibration).where(
        Calibration.project_id == project.id, Calibration.deleted_at.is_(None)
    )
    if check_key:
        q = q.where(Calibration.check_key == check_key)
    return list(db.scalars(q.order_by(Calibration.created_at.desc(), Calibration.id.desc())).all())


def get_calibration(db: Session, project: Project, calibration_id: uuid.UUID) -> Calibration:
    row = db.get(Calibration, calibration_id)
    if row is None or row.deleted_at is not None or row.project_id != project.id:
        raise NotFound("calibration not found")
    return row
