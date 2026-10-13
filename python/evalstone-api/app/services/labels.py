"""Human labels — the ground truth judges are calibrated against (library `Label` shape)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

from evalstone.checks.human import Label as LibLabel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.errors import Invalid, NotFound
from app.models import Label, Project, User

MAX_LABELS_PER_PUSH = 5000  # the schema's list cap reads this constant
# column widths the library does not bound; checked once here (422, not a DataError 500)
_LIMITS = {"sample_id": 200, "output_hash": 16, "check": 200, "labeler": 200, "notes": 5000}


def _check_lengths(labels: list[LibLabel]) -> None:
    for i, lb in enumerate(labels):
        for field, limit in _LIMITS.items():
            if len(getattr(lb, field) or "") > limit:
                raise Invalid(f"labels[{i}].{field} is longer than {limit} characters")


def _aware(dt: datetime) -> datetime:
    """A naive timestamp in a hand-edited labels.jsonl is taken as UTC, never session time."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def upsert(
    db: Session, *, project: Project, labels: list[LibLabel], labeler_user: User | None
) -> list[uuid.UUID]:
    """Later wins for the same (sample, output, check) — the library's LabelStore rule.

    A re-push also revives a soft-deleted label for the same key. Returns the ids of the
    rows written, in the order of the (deduplicated) input.
    """
    _check_lengths(labels)
    if not labels:
        return []
    last: dict[tuple[str, str, str], LibLabel] = {}
    for lb in labels:
        last[(lb.sample_id, lb.output_hash, lb.check or "")] = lb  # dedupe within the push
    values = [
        {
            "id": uuid.uuid4(),
            "project_id": project.id,
            "sample_key": lb.sample_id,
            "output_hash": lb.output_hash,
            "check_key": lb.check or "",
            "value": lb.value,
            "passed": lb.passed,
            "notes": lb.notes,
            "labeler": lb.labeler,
            "labeler_user_id": labeler_user.id if labeler_user else None,
            "labeled_at": _aware(lb.created_at),
            "raw": lb.raw,
        }
        for lb in last.values()
    ]
    stmt = insert(Label).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["project_id", "sample_key", "output_hash", "check_key"],
        set_={
            **{
                c: getattr(stmt.excluded, c)
                for c in (
                    "value",
                    "passed",
                    "notes",
                    "labeler",
                    "labeler_user_id",
                    "labeled_at",
                    "raw",
                )
            },
            "deleted_at": None,  # a re-push revives a deleted key
            "updated_at": func.now(),
        },
    )
    rows = db.execute(
        stmt.returning(Label.id, Label.sample_key, Label.output_hash, Label.check_key)
    ).all()
    db.commit()
    by_key = {(r.sample_key, r.output_hash, r.check_key): r.id for r in rows}
    return [by_key[(v["sample_key"], v["output_hash"], v["check_key"])] for v in values]


def list_labels(
    db: Session,
    project: Project,
    *,
    sample_key: str | None = None,
    check: str | None = None,
    offset: int = 0,
    limit: int = 200,
) -> tuple[list[Label], int]:
    q = select(Label).where(Label.project_id == project.id, Label.deleted_at.is_(None))
    if sample_key:
        q = q.where(Label.sample_key == sample_key)
    if check is not None:
        q = q.where(Label.check_key == check)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = list(
        db.scalars(
            q.order_by(Label.labeled_at.desc(), Label.id.desc()).offset(offset).limit(limit)
        ).all()
    )
    return rows, total


def lookup(
    db: Session, project: Project, *, sample_key: str, output_hash: str, check: str | None
) -> Label | None:
    """What the `human` check asks at run time."""
    return db.scalar(
        select(Label).where(
            Label.project_id == project.id,
            Label.sample_key == sample_key,
            Label.output_hash == output_hash,
            Label.check_key == (check or ""),
            Label.deleted_at.is_(None),
        )
    )


def iter_export(db: Session, project: Project) -> Iterator[str]:
    """Every live label as JSONL lines, oldest first, streamed (no cap, no count)."""
    q = (
        select(Label)
        .where(Label.project_id == project.id, Label.deleted_at.is_(None))
        .order_by(Label.labeled_at, Label.id)
        .execution_options(yield_per=500)
    )
    for row in db.scalars(q):
        yield to_library(row).model_dump_json() + "\n"


def to_library(row: Label) -> LibLabel:
    return LibLabel(
        sample_id=row.sample_key,
        output_hash=row.output_hash,
        value=row.value,
        passed=row.passed,
        notes=row.notes,
        check=row.check_key or None,
        labeler=row.labeler,
        created_at=row.labeled_at,
        raw=row.raw,
    )


def soft_delete(db: Session, project: Project, label_id: uuid.UUID) -> None:
    row = db.get(Label, label_id)
    if row is None or row.deleted_at is not None or row.project_id != project.id:
        raise NotFound("label not found")
    row.deleted_at = datetime.now(UTC)
    db.commit()
