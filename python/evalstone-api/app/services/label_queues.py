"""Labeling queues: materialise human tasks, hand them out, turn answers into labels.

A queue is built from a run (grade its outputs), two runs (compare A/B per sample) or a
dataset version (verify each `expected`). Finishing a task writes a library-shaped label
through the labels store (keyed by sample + output hash, so it is exactly what the
`human` check and calibration read); the task records which label it produced.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from evalstone.checks.human import Label as LibLabel
from evalstone.checks.human import output_hash
from evalstone.output import Output
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.errors import Conflict, Invalid, NotFound
from app.models import (
    DatasetVersion,
    Label,
    LabelQueue,
    LabelTask,
    Project,
    Run,
    RunResult,
    User,
)
from app.models.label_queue import QUEUE_KINDS
from app.services import datasets as dataset_svc
from app.services import labels as label_svc
from app.services import runs as run_svc

MAX_TASKS_PER_QUEUE = 5000


def _hash_of(output_json: dict[str, Any]) -> str:
    return output_hash(Output.model_validate(output_json))


# --- building ---------------------------------------------------------------------------------


def _grade_items(db: Session, run: Run, *, check_key: str | None, failed_only: bool) -> list[dict]:
    rows, _ = run_svc.list_results(
        db,
        run,
        check_key=check_key or None,
        failed_only=failed_only,
        offset=0,
        limit=MAX_TASKS_PER_QUEUE + 1,
    )
    seen: set[str] = set()
    items = []
    for r in rows:
        if r.sample_key in seen:
            continue  # one task per sample, whatever the number of checks
        seen.add(r.sample_key)
        items.append(
            {
                "sample_key": r.sample_key,
                "output_hash": _hash_of(r.output),
                "payload": {
                    "input": r.input,
                    "expected": r.expected,
                    "output": r.output,
                    "run_id": str(run.id),
                    "result_id": str(r.id),
                    "check_key": r.check_key,
                    "machine": {"score": r.score, "passed": r.passed, "reason": r.reason},
                },
            }
        )
    return items


def _compare_items(db: Session, a: Run, b: Run) -> list[dict]:
    ra = {r.sample_key: r for r in db.scalars(select(RunResult).where(RunResult.run_id == a.id))}
    rb = {r.sample_key: r for r in db.scalars(select(RunResult).where(RunResult.run_id == b.id))}
    items = []
    for key in sorted(set(ra) & set(rb)):
        items.append(
            {
                "sample_key": key,
                "output_hash": _hash_of(ra[key].output),
                "payload": {
                    "input": ra[key].input,
                    "expected": ra[key].expected,
                    "a": {
                        "run_id": str(a.id),
                        "output": ra[key].output,
                        "hash": _hash_of(ra[key].output),
                    },
                    "b": {
                        "run_id": str(b.id),
                        "output": rb[key].output,
                        "hash": _hash_of(rb[key].output),
                    },
                },
            }
        )
    return items


def _verify_items(db: Session, version: DatasetVersion) -> list[dict]:
    rows, _ = dataset_svc.version_samples(db, version, offset=0, limit=MAX_TASKS_PER_QUEUE + 1)
    return [
        {
            "sample_key": s.sample_key,
            "output_hash": output_hash(Output(value=s.expected)),
            "payload": {
                "input": s.input,
                "expected": s.expected,
                "sample_id": str(s.id),
                "dataset_version_id": str(version.id),
            },
        }
        for s in rows
    ]


def create(
    db: Session,
    *,
    project: Project,
    name: str,
    kind: str,
    source: dict[str, Any],
    instructions: str = "",
    check_key: str = "",
    scale: int = 5,
    due_at: datetime | None = None,
    created_by: User | None,
) -> LabelQueue:
    if kind not in QUEUE_KINDS:
        raise Invalid(f"kind must be one of {', '.join(QUEUE_KINDS)}")
    if scale < 2 or scale > 10:
        raise Invalid("scale must be 2 (pass/fail) .. 10")
    if kind == "grade":
        run = run_svc.get_run(db, project, _uuid(source.get("run_id"), "source.run_id"))
        items = _grade_items(
            db, run, check_key=source.get("check_key"), failed_only=bool(source.get("failed_only"))
        )
    elif kind == "compare":
        a = run_svc.get_run(db, project, _uuid(source.get("run_a"), "source.run_a"))
        b = run_svc.get_run(db, project, _uuid(source.get("run_b"), "source.run_b"))
        if a.id == b.id:
            raise Invalid("compare needs two different runs")
        items = _compare_items(db, a, b)
    else:
        ds = dataset_svc.get_dataset(
            db, project, _uuid(source.get("dataset_id"), "source.dataset_id")
        )
        version = dataset_svc.get_version(db, ds, int(source.get("version") or 0))
        items = _verify_items(db, version)
    if not items:
        raise Invalid("the source yields no tasks")
    if len(items) > MAX_TASKS_PER_QUEUE:
        raise Invalid(f"at most {MAX_TASKS_PER_QUEUE} tasks per queue; narrow the source")
    queue = LabelQueue(
        project_id=project.id,
        name=name,
        kind=kind,
        instructions=instructions,
        check_key=check_key,
        scale=scale,
        source=source,
        due_at=due_at,
        task_count=len(items),
        created_by_user_id=created_by.id if created_by else None,
    )
    db.add(queue)
    db.flush()
    db.add_all(
        LabelTask(queue_id=queue.id, project_id=project.id, position=i, **item)
        for i, item in enumerate(items)
    )
    db.commit()
    db.refresh(queue)
    return queue


def _uuid(value: Any, where: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as err:
        raise Invalid(f"{where} must be a uuid") from err


# --- reading ----------------------------------------------------------------------------------


def list_queues(db: Session, project: Project) -> list[LabelQueue]:
    return list(
        db.scalars(
            select(LabelQueue)
            .where(LabelQueue.project_id == project.id, LabelQueue.deleted_at.is_(None))
            .order_by(LabelQueue.created_at.desc(), LabelQueue.id.desc())
        ).all()
    )


def get_queue(db: Session, project: Project, queue_id: uuid.UUID) -> LabelQueue:
    q = db.get(LabelQueue, queue_id)
    if q is None or q.deleted_at is not None or q.project_id != project.id:
        raise NotFound("label queue not found")
    return q


def progress(db: Session, queue: LabelQueue) -> dict[str, int]:
    rows = db.execute(
        select(LabelTask.status, func.count())
        .where(LabelTask.queue_id == queue.id)
        .group_by(LabelTask.status)
    ).all()
    counts = {"pending": 0, "done": 0, "skipped": 0, **{s: n for s, n in rows}}
    counts["total"] = queue.task_count
    counts["claimed"] = db.scalar(
        select(func.count()).where(
            LabelTask.queue_id == queue.id,
            LabelTask.status == "pending",
            LabelTask.assignee_user_id.is_not(None),
        )
    )
    return counts


def list_tasks(
    db: Session,
    queue: LabelQueue,
    *,
    status: str | None = None,
    assignee_user_id: uuid.UUID | None = None,
    offset: int = 0,
    limit: int = 100,
) -> tuple[list[LabelTask], int]:
    q = select(LabelTask).where(LabelTask.queue_id == queue.id)
    if status:
        q = q.where(LabelTask.status == status)
    if assignee_user_id is not None:
        q = q.where(LabelTask.assignee_user_id == assignee_user_id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = list(db.scalars(q.order_by(LabelTask.position).offset(offset).limit(limit)).all())
    return rows, total


def get_task(db: Session, project: Project, task_id: uuid.UUID) -> LabelTask:
    t = db.get(LabelTask, task_id)
    if t is None or t.project_id != project.id:
        raise NotFound("task not found")
    return t


# --- assignment -------------------------------------------------------------------------------


def assign(db: Session, queue: LabelQueue, user_ids: list[uuid.UUID]) -> int:
    """Round-robin the UNASSIGNED pending tasks over `user_ids`; returns how many were assigned."""
    if not user_ids:
        raise Invalid("give at least one user")
    pending = list(
        db.scalars(
            select(LabelTask)
            .where(
                LabelTask.queue_id == queue.id,
                LabelTask.status == "pending",
                LabelTask.assignee_user_id.is_(None),
            )
            .order_by(LabelTask.position)
            .with_for_update(skip_locked=True)
        ).all()
    )
    for i, task in enumerate(pending):
        task.assignee_user_id = user_ids[i % len(user_ids)]
    db.commit()
    return len(pending)


def claim_next(db: Session, queue: LabelQueue, user: User) -> LabelTask | None:
    """The next pending task for `user`: one already assigned to them, else an unassigned one
    (claimed atomically with SKIP LOCKED so two labelers never get the same task)."""
    if queue.status != "open":
        raise Conflict("queue is closed")
    mine = db.scalar(
        select(LabelTask)
        .where(
            LabelTask.queue_id == queue.id,
            LabelTask.status == "pending",
            LabelTask.assignee_user_id == user.id,
        )
        .order_by(LabelTask.position)
        .limit(1)
    )
    if mine is not None:
        return mine
    row = db.scalar(
        update(LabelTask)
        .where(
            LabelTask.id
            == select(LabelTask.id)
            .where(
                LabelTask.queue_id == queue.id,
                LabelTask.status == "pending",
                LabelTask.assignee_user_id.is_(None),
            )
            .order_by(LabelTask.position)
            .limit(1)
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )
        .values(assignee_user_id=user.id, claimed_at=func.now())
        .returning(LabelTask)
    )
    db.commit()
    return row


# --- answering --------------------------------------------------------------------------------


def _value_from(
    queue: LabelQueue, *, grade: int | None, passed: bool | None
) -> tuple[float, bool, Any]:
    """The library's convention: value = (grade-1)/(scale-1); pass at the top level on a 2-point
    scale, else at the second-highest (the judge's default)."""
    if grade is None:
        if passed is None:
            raise Invalid("give a grade (1..scale) or passed")
        return (1.0 if passed else 0.0), passed, None
    if not 1 <= grade <= queue.scale:
        raise Invalid(f"grade must be within 1..{queue.scale}")
    value = (grade - 1) / (queue.scale - 1)
    level = queue.scale if queue.scale == 2 else queue.scale - 1
    return value, (passed if passed is not None else grade >= level), grade


def complete(
    db: Session,
    *,
    queue: LabelQueue,
    task: LabelTask,
    user: User,
    grade: int | None,
    passed: bool | None,
    notes: str,
    winner: str | None,
) -> LabelTask:
    if queue.status != "open":
        raise Conflict("queue is closed")
    if task.queue_id != queue.id:
        raise NotFound("task not found in this queue")
    if task.status == "done":
        raise Conflict("task already done")
    if task.assignee_user_id not in (None, user.id):
        raise Conflict("task is assigned to someone else")
    raw: dict[str, Any] = {"queue_id": str(queue.id), "task_id": str(task.id)}
    if queue.kind == "compare":
        if winner not in ("a", "b", "tie"):
            raise Invalid("a compare task needs winner: a | b | tie")
        value, ok = {"a": (1.0, True), "b": (0.0, False), "tie": (0.5, False)}[winner]
        raw["comparison"] = {
            "winner": winner,
            "a": task.payload["a"]["hash"],
            "b": task.payload["b"]["hash"],
        }
        grade_raw: Any = winner
    else:
        value, ok, grade_raw = _value_from(queue, grade=grade, passed=passed)
    raw["grade"] = grade_raw
    label = LibLabel(
        sample_id=task.sample_key,
        output_hash=task.output_hash,
        value=value,
        passed=ok,
        notes=notes,
        check=queue.check_key or None,
        labeler=user.email,
        raw=raw,
    )
    project = db.get(Project, task.project_id)
    label_svc.upsert(db, project=project, labels=[label], labeler_user=user)
    stored = label_svc.lookup(
        db,
        project,
        sample_key=task.sample_key,
        output_hash=task.output_hash,
        check=queue.check_key or None,
    )
    task.status, task.done_at, task.label_id = (
        "done",
        datetime.now(UTC),
        stored.id if stored else None,
    )
    task.assignee_user_id = task.assignee_user_id or user.id
    db.commit()
    db.refresh(task)
    return task


def skip(db: Session, task: LabelTask, user: User, *, reason: str = "") -> LabelTask:
    if task.status == "done":
        raise Conflict("task already done")
    task.status = "skipped"
    task.payload = {**task.payload, "skip_reason": reason}
    task.assignee_user_id = task.assignee_user_id or user.id
    task.done_at = datetime.now(UTC)
    db.commit()
    db.refresh(task)
    return task


def close(db: Session, queue: LabelQueue, *, status: str) -> LabelQueue:
    if status not in ("open", "closed"):
        raise Invalid("status must be open or closed")
    queue.status = status
    db.commit()
    db.refresh(queue)
    return queue


def label_of(db: Session, task: LabelTask) -> Label | None:
    return db.get(Label, task.label_id) if task.label_id else None
