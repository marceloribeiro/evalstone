"""Judge calibration: a judge version against the humans, on what both have graded.

`judges()` lists the judge versions seen in the project's run results (stamped at ingest
from the library's `raw.judge_version` / `raw.judge_model`, else `raw.model`). `compute()`
joins — in SQL — the latest non-errored verdict per (sample, output hash) of one version
with the labels of the same key and reports agreement, Cohen's kappa, a pass/fail confusion
matrix and the mean absolute error of the 0..1 values. The job runs in Celery
(`app.tasks.calibrate`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by, distinct_on
from sqlalchemy.orm import Session

from app.errors import Invalid, NotFound
from app.models import Calibration, Label, Project, Run, RunResult, User
from app.services import events

MAX_PAIRS = 50_000  # labelled outputs a calibration may cover; above it the job fails loudly


def judges(db: Session, project: Project) -> list[dict[str, Any]]:
    """Every (check_key, judge_version) with its model, result and run counts and when seen.

    `model` is the `<provider>/<model>` the most recent verdict was routed through (results
    from a library before 0.2.3 carry the provider-reported id instead, so the newest stamp
    wins over an older library's on the same version).
    """
    rows = db.execute(
        select(
            RunResult.check_key,
            RunResult.judge_version,
            # the newest verdict's stamp, by run finish time like compute() (1-based index)
            func.array_agg(
                aggregate_order_by(
                    RunResult.judge_model,
                    Run.finished_at.desc(),
                    RunResult.created_at.desc(),
                    RunResult.id.desc(),
                )
            )[1],
            func.count(),
            func.count(func.distinct(RunResult.run_id)),
            func.min(RunResult.created_at),
            func.max(RunResult.created_at),
        )
        .join(Run, Run.id == RunResult.run_id)
        .where(
            Run.project_id == project.id,
            Run.deleted_at.is_(None),
            RunResult.judge_version.is_not(None),
        )
        .group_by(RunResult.check_key, RunResult.judge_version)
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


def latest_version(db: Session, project: Project, check_key: str) -> str | None:
    """The judge version of the most recently FINISHED run that graded `check_key`."""
    return db.scalar(
        select(RunResult.judge_version)
        .join(Run, Run.id == RunResult.run_id)
        .where(
            Run.project_id == project.id,
            Run.deleted_at.is_(None),
            RunResult.check_key == check_key,
            RunResult.judge_version.is_not(None),
        )
        .order_by(Run.finished_at.desc(), RunResult.created_at.desc(), RunResult.id.desc())
        .limit(1)
    )


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
    """Latest verdict per labelled (sample, output) — by the run's finish time, not ingest
    time, so a backfilled older run never overrides a newer verdict — joined to the label."""
    labelled = (
        select(func.count())
        .select_from(Label)
        .where(
            Label.project_id == project.id,
            Label.check_key == label_check,
            Label.deleted_at.is_(None),
        )
    )
    n_labels = db.scalar(labelled)
    if not n_labels:
        raise Invalid(f"no human labels under check {label_check!r} in this project")
    if n_labels > MAX_PAIRS:
        raise Invalid(f"{n_labels} labels under {label_check!r}; the limit is {MAX_PAIRS}")
    latest = (
        select(
            RunResult.sample_key,
            RunResult.output_hash,
            RunResult.passed,
            RunResult.score,
            RunResult.judge_model,
            Run.finished_at,
            RunResult.created_at,
        )
        .join(Run, Run.id == RunResult.run_id)
        .where(
            Run.project_id == project.id,
            Run.deleted_at.is_(None),
            RunResult.check_key == check_key,
            RunResult.judge_version == judge_version,
            RunResult.error.is_(None),  # an error is never a verdict
            RunResult.skipped.is_(False),
        )
        .ext(distinct_on(RunResult.sample_key, RunResult.output_hash))
        .order_by(
            RunResult.sample_key,
            RunResult.output_hash,
            Run.finished_at.desc(),
            RunResult.created_at.desc(),  # uuid ids are random: ingest time breaks ties
            RunResult.id.desc(),
        )
        .subquery()
    )
    pairs = db.execute(
        select(
            latest.c.passed,
            latest.c.score,
            latest.c.judge_model,
            latest.c.finished_at,
            latest.c.created_at,
            Label.passed,
            Label.value,
        )
        .join(
            Label,
            (Label.sample_key == latest.c.sample_key) & (Label.output_hash == latest.c.output_hash),
        )
        .where(
            Label.project_id == project.id,
            Label.check_key == label_check,
            Label.deleted_at.is_(None),
        )
        .execution_options(yield_per=1000)
    )
    tp = fp = fn = tn = 0
    abs_err = 0.0
    model: str | None = None
    newest: tuple[datetime, datetime] | None = None  # the model of the most recent verdict
    for (
        judge_passed,
        judge_value,
        judge_model,
        finished,
        created,
        human_passed,
        human_value,
    ) in pairs:
        if judge_model and (newest is None or (finished, created) > newest):
            model, newest = judge_model, (finished, created)
        if judge_passed and human_passed:
            tp += 1
        elif judge_passed and not human_passed:
            fp += 1
        elif not judge_passed and human_passed:
            fn += 1
        else:
            tn += 1
        abs_err += abs(judge_value - human_value)
    n = tp + fp + fn + tn
    if n == 0:
        raise Invalid(
            f"no overlap: none of the {n_labels} labelled outputs has a verdict from "
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
    """Queue a calibration (the latest judge version of the check when none is given).

    A broker failure marks the row `failed` with the error instead of orphaning a `queued` row.
    """
    if judge_version is None:
        judge_version = latest_version(db, project, check_key)
        if judge_version is None:
            raise Invalid(f"no judge verdicts for check {check_key!r} in this project")
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

    try:
        calibrate.delay(str(row.id))
    except Exception as exc:
        row.status, row.error = "failed", f"could not enqueue: {type(exc).__name__}: {exc}"[:1000]
        row.finished_at = datetime.now(UTC)
        db.commit()
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
        db.rollback()  # a DB error leaves the transaction aborted; recover before writing
        row = db.get(Calibration, calibration_id)
        row.status, row.error = "failed", f"{type(exc).__name__}: {str(exc)[:900]}"
        row.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        events.publish(
            row.project_id,
            "calibration.finished",
            calibration_id=row.id,
            status="failed",
            check_key=row.check_key,
            error=row.error,
        )
        return row
    for k, v in stats.items():
        setattr(row, k, v)
    row.status, row.finished_at = "done", datetime.now(UTC)
    db.commit()
    db.refresh(row)
    events.publish(
        row.project_id,
        "calibration.finished",
        calibration_id=row.id,
        status=row.status,
        check_key=row.check_key,
        judge_version=row.judge_version,
        agreement=row.agreement,
        kappa=row.kappa,
        n=row.n,
    )
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
