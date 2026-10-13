"""Run history: the library's report, stored once per (project, client run id).

The report is validated with the library's own `Run` model, results are flattened into
rows, the dataset version is linked by content hash when the center has it, and `compare`
is the library's `compare()` over runs rebuilt from the rows, so the CLI, the MCP server
and the center agree on what a regression is.
"""

from __future__ import annotations

import uuid
from typing import Any

from evalstone._json import canonical
from evalstone.checks.human import output_hash
from evalstone.output import Output
from evalstone.run import Comparison, Result, summarise
from evalstone.run import Run as LibRun
from evalstone.run import compare as lib_compare
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.errors import Invalid, NotFound
from app.models import Dataset, DatasetVersion, Project, Run, RunResult, User
from app.services import events

MAX_RESULTS_PER_RUN = 20_000


def output_hash_of(output_json: dict[str, Any]) -> str:
    """The library's hash of a stored output JSON — the key labels and tasks use."""
    return output_hash(Output.model_validate(output_json))


def _judge_stamp(raw: Any) -> tuple[str | None, str | None]:
    if not isinstance(raw, dict):
        return None, None
    jv, model = raw.get("judge_version"), raw.get("model")
    jv = str(jv)[:16] if isinstance(jv, str) and jv else None
    model = str(model)[:200] if isinstance(model, str) and model else None
    return jv, model


MAX_RESULT_BYTES = 256 * 1024  # canonical JSON of one result (input, expected, output, score)
# column widths the library does not bound; checked here so an over-long value is a 422
_LIMITS = {"id": 64, "git_sha": 64, "trigger": 40, "suite": 200, "dataset": 200}
_RESULT_LIMITS = {"sample_id": 200, "check_key": 200}


def get_run(db: Session, project: Project, run_id: uuid.UUID) -> Run:
    r = db.get(Run, run_id)
    if r is None or r.deleted_at is not None or r.project_id != project.id:
        raise NotFound("run not found")
    return r


def by_client_id(db: Session, project_id: uuid.UUID, client_run_id: str) -> Run | None:
    return db.scalar(
        select(Run).where(
            Run.project_id == project_id,
            Run.client_run_id == client_run_id,
            Run.deleted_at.is_(None),
        )
    )


def list_runs(
    db: Session,
    project: Project,
    *,
    suite: str | None = None,
    baseline_only: bool = False,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Run], int]:
    q = select(Run).where(Run.project_id == project.id, Run.deleted_at.is_(None))
    if suite:
        q = q.where(Run.suite == suite)
    if baseline_only:
        q = q.where(Run.is_baseline.is_(True))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = list(
        db.scalars(
            q.order_by(Run.started_at.desc(), Run.id.desc()).offset(offset).limit(limit)
        ).all()
    )
    return rows, total


def _validate(report: dict[str, Any]) -> LibRun:
    try:
        run = LibRun.model_validate(report)
    except (ValueError, TypeError) as err:
        raise Invalid(f"invalid run report: {str(err)[:500]}") from err
    if len(run.results) > MAX_RESULTS_PER_RUN:
        raise Invalid(f"at most {MAX_RESULTS_PER_RUN} results per run")
    for field, limit in _LIMITS.items():
        value = getattr(run, field)
        if value is not None and len(value) > limit:
            raise Invalid(f"{field} is longer than {limit} characters")
    seen: set[tuple[str, str]] = set()
    for i, r in enumerate(run.results):
        for field, limit in _RESULT_LIMITS.items():
            if len(getattr(r, field)) > limit:
                raise Invalid(f"results[{i}].{field} is longer than {limit} characters")
        size = len(canonical(r.model_dump(mode="json")).encode())
        if size > MAX_RESULT_BYTES:
            raise Invalid(
                f"results[{i}] ({r.sample_id}/{r.check_key}) is {size} bytes; "
                f"the limit is {MAX_RESULT_BYTES} bytes of canonical JSON"
            )
        k = (r.sample_id, r.check_key)
        if k in seen:
            raise Invalid(f"duplicate result for sample {r.sample_id!r} check {r.check_key!r}")
        seen.add(k)
    return run


def _recomputed_summary(run: LibRun):
    """The summary the library derives from these results, not the one the client asserted.

    A client-asserted pass rate next to row-derived flips in compare() would disagree; the
    duration is the one value only the client knows.
    """
    return summarise(
        run.results,
        samples=len({r.sample_id for r in run.results}),
        checks=len(run.check_keys),
        duration_ms=run.summary.duration_ms,
    )


def ingest(
    db: Session, *, project: Project, report: dict[str, Any], created_by: User | None
) -> tuple[Run, bool]:
    """Store a library report. Same client run id → (existing, False).

    The project row is locked for the transaction so a retry of a slow push (the CLI timing
    out and sending again) waits for the first insert and gets the stored run back.
    """
    lib = _validate(report)
    summary = _recomputed_summary(lib)
    db.execute(select(Project.id).where(Project.id == project.id).with_for_update())
    existing = by_client_id(db, project.id, lib.id)
    if existing is not None:
        db.rollback()  # release the lock; nothing to write
        return existing, False
    version = db.scalar(
        select(DatasetVersion)
        .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
        .where(
            Dataset.project_id == project.id,
            Dataset.deleted_at.is_(None),
            DatasetVersion.content_hash == lib.dataset_hash,
        )
        .order_by((Dataset.name == lib.dataset).desc(), DatasetVersion.created_at)
        .limit(1)
    )
    baseline = by_client_id(db, project.id, lib.baseline_run_id) if lib.baseline_run_id else None
    row = Run(
        project_id=project.id,
        client_run_id=lib.id,
        suite=lib.suite,
        dataset_name=lib.dataset,
        dataset_hash=lib.dataset_hash,
        dataset_version_id=version.id if version else None,
        target=lib.target,
        check_keys=list(lib.check_keys),
        git_sha=lib.git_sha,
        trigger=lib.trigger,
        baseline_run_id=baseline.id if baseline else None,
        client_baseline_run_id=lib.baseline_run_id,
        started_at=lib.started_at,
        finished_at=lib.finished_at,
        summary=summary.model_dump(mode="json"),
        pass_rate=summary.pass_rate,
        mean_score=summary.mean_score,
        error_rate=summary.error_rate,
        cost_usd=summary.cost_usd,
        duration_ms=summary.duration_ms,
        result_count=len(lib.results),
        gate_passed=lib.gate_passed,
        gate_lines=list(lib.gate_lines),
        created_by_user_id=created_by.id if created_by else None,
    )
    db.add(row)
    db.flush()
    db.add_all(
        RunResult(
            run_id=row.id,
            position=i,
            sample_key=r.sample_id,
            check_key=r.check_key,
            tags=list(r.tags),
            input=r.input,
            expected=r.expected,
            output=r.output.model_dump(mode="json"),
            output_hash=output_hash_of(r.output.model_dump(mode="json")),
            judge_version=_judge_stamp(r.score.raw)[0],
            judge_model=_judge_stamp(r.score.raw)[1],
            score=r.score.value,
            passed=r.score.passed,
            reason=r.score.reason,
            cost_usd=r.score.cost_usd,
            latency_ms=r.score.latency_ms,
            error=r.score.error,
            skipped=r.score.skipped,
            raw=r.score.raw,
        )
        for i, r in enumerate(lib.results)
    )
    db.commit()
    db.refresh(row)
    events.publish(
        project.id,
        "run.stored",
        run_id=row.id,
        client_run_id=row.client_run_id,
        suite=row.suite,
        pass_rate=row.pass_rate,
        result_count=row.result_count,
    )
    return row, True


def list_results(
    db: Session,
    run: Run,
    *,
    check_key: str | None = None,
    failed_only: bool = False,
    offset: int = 0,
    limit: int = 200,
) -> tuple[list[RunResult], int]:
    q = select(RunResult).where(RunResult.run_id == run.id)
    if check_key:
        q = q.where(RunResult.check_key == check_key)
    if failed_only:
        q = q.where(RunResult.passed.is_(False))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = list(
        db.scalars(
            q.order_by(RunResult.sample_key, RunResult.check_key).offset(offset).limit(limit)
        ).all()
    )
    return rows, total


def to_library_run(db: Session, run: Run) -> LibRun:
    """Rebuild the library's Run from the rows (what the CLI would have written)."""
    rows = db.scalars(
        select(RunResult).where(RunResult.run_id == run.id).order_by(RunResult.position)
    ).all()
    results = [
        Result(
            sample_id=r.sample_key,
            check_key=r.check_key,
            tags=list(r.tags or []),
            input=r.input,
            expected=r.expected,
            output=r.output,
            score={
                "value": r.score,
                "passed": r.passed,
                "reason": r.reason,
                "cost_usd": r.cost_usd,
                "latency_ms": r.latency_ms,
                "error": r.error,
                "raw": r.raw,
                "skipped": r.skipped,
            },
        )
        for r in rows
    ]
    return LibRun(
        id=run.client_run_id,
        suite=run.suite,
        dataset=run.dataset_name,
        dataset_hash=run.dataset_hash,
        target=run.target,
        check_keys=list(run.check_keys),
        git_sha=run.git_sha,
        trigger=run.trigger,
        baseline_run_id=run.client_baseline_run_id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        results=results,
        summary=run.summary,
        gate_passed=run.gate_passed,
        gate_lines=list(run.gate_lines or []),
    )


def compare_runs(db: Session, a: Run, b: Run) -> Comparison:
    return lib_compare(to_library_run(db, a), to_library_run(db, b))


def set_baseline(db: Session, run: Run, *, value: bool) -> Run:
    """At most one baseline per (project, suite): marking one unmarks the previous.

    `uq_run_suite_baseline` enforces it in the database; two concurrent marks on different
    runs cannot both win (the loser gets 409 from the IntegrityError handler).
    """
    if value:
        db.execute(
            update(Run)
            .where(
                Run.project_id == run.project_id,
                Run.suite == run.suite,
                Run.is_baseline.is_(True),
                Run.id != run.id,
            )
            .values(is_baseline=False)
        )
        db.flush()
    run.is_baseline = value
    db.commit()
    db.refresh(run)
    return run
