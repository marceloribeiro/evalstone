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
    LabelQueue,
    LabelTask,
    OrganizationMember,
    Project,
    Run,
    RunResult,
    User,
)
from app.models.label_queue import QUEUE_KINDS, TASK_STATUSES
from app.services import datasets as dataset_svc
from app.services import labels as label_svc
from app.services import runs as run_svc

MAX_TASKS_PER_QUEUE = 5000


_hash_of = run_svc.output_hash_of  # one rule for hashing a stored output


# --- building ---------------------------------------------------------------------------------


def _grade_items(db: Session, run: Run, *, check_key: str | None, failed_only: bool) -> list[dict]:
    """One task per DISTINCT sample (whatever the number of checks); capped before building."""
    cond = [RunResult.run_id == run.id]
    if check_key:
        cond.append(RunResult.check_key == check_key)
    if failed_only:
        cond.append(RunResult.passed.is_(False))
    keys = list(
        db.scalars(
            select(RunResult.sample_key)
            .where(*cond)
            .group_by(RunResult.sample_key)
            .order_by(RunResult.sample_key)
            .limit(MAX_TASKS_PER_QUEUE + 1)
        ).all()
    )
    _cap(len(keys))
    rows = db.scalars(
        select(RunResult)
        .where(*cond, RunResult.sample_key.in_(keys))
        .order_by(RunResult.sample_key, RunResult.check_key)
    ).all()
    items, seen = [], set()
    for r in rows:
        if r.sample_key in seen:
            continue  # the first (alphabetical) check's result carries the output
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


def _cap(n: int) -> None:
    if n > MAX_TASKS_PER_QUEUE:
        raise Invalid(f"at most {MAX_TASKS_PER_QUEUE} tasks per queue; narrow the source")
    if n == 0:
        raise Invalid("the source yields no tasks")


def _compare_items(db: Session, a: Run, b: Run) -> list[dict]:
    """One task per sample both runs share; the shared-key count is checked before loading."""
    ka = select(RunResult.sample_key).where(RunResult.run_id == a.id)
    kb = select(RunResult.sample_key).where(RunResult.run_id == b.id)
    shared = sorted(db.scalars(ka.intersect(kb).limit(MAX_TASKS_PER_QUEUE + 1)).all())
    _cap(len(shared))

    def first_results(run: Run) -> dict[str, RunResult]:
        out: dict[str, RunResult] = {}
        for r in db.scalars(
            select(RunResult)
            .where(RunResult.run_id == run.id, RunResult.sample_key.in_(shared))
            .order_by(RunResult.sample_key, RunResult.check_key)
        ):
            out.setdefault(r.sample_key, r)
        return out

    first_a, first_b = first_results(a), first_results(b)
    items = []
    for key in shared:
        ra, rb = first_a[key], first_b[key]
        hash_a, hash_b = _hash_of(ra.output), _hash_of(rb.output)
        items.append(
            {
                "sample_key": key,
                "output_hash": hash_a,
                "payload": {
                    "input": ra.input,
                    "expected": ra.expected,
                    "a": {"run_id": str(a.id), "output": ra.output, "hash": hash_a},
                    "b": {"run_id": str(b.id), "output": rb.output, "hash": hash_b},
                },
            }
        )
    return items


def _verify_items(db: Session, version: DatasetVersion) -> list[dict]:
    rows, _ = dataset_svc.version_samples(db, version, offset=0, limit=MAX_TASKS_PER_QUEUE + 1)
    _cap(len(rows))
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
    if kind == "compare" and check_key:
        raise Invalid(
            "a compare queue stores verdicts under 'compare:<run_b>'; leave check_key empty"
        )
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
        version = dataset_svc.get_version(db, ds, _int(source.get("version"), "source.version"))
        items = _verify_items(db, version)
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


def _int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str) or str(value).strip() == "":
        raise Invalid(f"{where} must be an integer")
    try:
        return int(str(value))
    except ValueError as err:
        raise Invalid(f"{where} must be an integer") from err


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
        if status not in TASK_STATUSES:
            raise Invalid(f"status must be one of {', '.join(TASK_STATUSES)}")
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


def _members_only(db: Session, project: Project, user_ids: list[uuid.UUID]) -> None:
    members = set(
        db.scalars(
            select(OrganizationMember.user_id).where(
                OrganizationMember.organization_id == project.organization_id,
                OrganizationMember.user_id.in_(user_ids),
                OrganizationMember.deleted_at.is_(None),
            )
        ).all()
    )
    unknown = sorted(str(u) for u in set(user_ids) - members)
    if unknown:
        raise Invalid(f"not members of this organization: {', '.join(unknown)}")


def assign(db: Session, project: Project, queue: LabelQueue, user_ids: list[uuid.UUID]) -> int:
    """Round-robin the UNASSIGNED pending tasks over `user_ids` (org members); returns the count."""
    if not user_ids:
        raise Invalid("give at least one user")
    _members_only(db, project, user_ids)
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
    now = datetime.now(UTC)
    for i, task in enumerate(pending):
        task.assignee_user_id, task.claimed_at = user_ids[i % len(user_ids)], now
    db.commit()
    return len(pending)


def unassign(db: Session, queue: LabelQueue, user_ids: list[uuid.UUID] | None) -> int:
    """Release pending tasks held by `user_ids` (every assignee when None) back to the pool."""
    q = (
        update(LabelTask)
        .where(
            LabelTask.queue_id == queue.id,
            LabelTask.status == "pending",
            LabelTask.assignee_user_id.is_not(None),
        )
        .values(assignee_user_id=None, claimed_at=None)
    )
    if user_ids:
        q = q.where(LabelTask.assignee_user_id.in_(user_ids))
    n = db.execute(q).rowcount
    db.commit()
    return n


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
        if mine.claimed_at is None:
            mine.claimed_at = datetime.now(UTC)
            db.commit()
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


def _guard(queue: LabelQueue, task: LabelTask, user: User) -> None:
    """The invariants every verdict on a task shares (answer and skip alike)."""
    if task.queue_id != queue.id:
        raise NotFound("task not found in this queue")
    if queue.status != "open":
        raise Conflict("queue is closed")
    if task.status != "pending":
        raise Conflict(f"task already {task.status}")
    if task.assignee_user_id not in (None, user.id):
        raise Conflict("task is assigned to someone else")


def compare_check_key(task: LabelTask) -> str:
    """A compare verdict is a label on output A **relative to run B**, under its own check
    key, so it never overwrites or masquerades as an absolute grade of A."""
    return f"compare:{task.payload['b']['run_id']}"


def complete(
    db: Session,
    *,
    project: Project,
    queue: LabelQueue,
    task: LabelTask,
    user: User,
    grade: int | None,
    passed: bool | None,
    notes: str,
    winner: str | None,
) -> LabelTask:
    _guard(queue, task, user)
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
        check, grade_raw = compare_check_key(task), winner
    else:
        value, ok, grade_raw = _value_from(queue, grade=grade, passed=passed)
        check = queue.check_key or None
    raw["grade"] = grade_raw
    label = LibLabel(
        sample_id=task.sample_key,
        output_hash=task.output_hash,
        value=value,
        passed=ok,
        notes=notes,
        check=check,
        labeler=user.email,
        raw=raw,
    )
    ids = label_svc.upsert(db, project=project, labels=[label], labeler_user=user)
    task.status, task.done_at, task.label_id = "done", datetime.now(UTC), ids[0]
    task.assignee_user_id = task.assignee_user_id or user.id
    db.commit()
    db.refresh(task)
    return task


def skip(
    db: Session, queue: LabelQueue, task: LabelTask, user: User, *, reason: str = ""
) -> LabelTask:
    _guard(queue, task, user)
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
