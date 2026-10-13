"""Datasets, immutable versions and content-addressed samples.

Hashes are computed with the library's own code (`evalstone.dataset.Sample`,
`evalstone._json.sha256`) so a version pushed from the CLI has the same `content_hash`
the center stores, and the same sample ids.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from evalstone._json import canonical, sha256
from evalstone.dataset import Sample as LibSample
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.errors import Conflict, Invalid, NotFound
from app.models import Dataset, DatasetVersion, DatasetVersionSample, Project, Sample, User

MAX_SAMPLES_PER_VERSION = 5000  # the schema's list cap reads this constant
MAX_SAMPLE_BYTES = 64 * 1024  # canonical JSON of one sample (input + expected + metadata + tags)


def list_datasets(db: Session, project: Project) -> list[Dataset]:
    return list(
        db.scalars(
            select(Dataset)
            .where(Dataset.project_id == project.id, Dataset.deleted_at.is_(None))
            .order_by(Dataset.created_at)
        ).all()
    )


def get_dataset(db: Session, project: Project, dataset_id: uuid.UUID) -> Dataset:
    d = db.get(Dataset, dataset_id)
    if d is None or d.deleted_at is not None or d.project_id != project.id:
        raise NotFound("dataset not found")
    return d


def get_by_name(db: Session, project_id: uuid.UUID, name: str) -> Dataset | None:
    return db.scalar(
        select(Dataset).where(
            Dataset.project_id == project_id, Dataset.name == name, Dataset.deleted_at.is_(None)
        )
    )


def create(
    db: Session,
    *,
    project: Project,
    name: str,
    description: str = "",
    tags: list[str] | None = None,
) -> Dataset:
    if get_by_name(db, project.id, name) is not None:
        raise Conflict(f"dataset '{name}' already exists in this project")
    d = Dataset(project_id=project.id, name=name, description=description, tags=list(tags or []))
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def update(db: Session, d: Dataset, **fields) -> Dataset:
    renamed = fields.get("name") and fields["name"] != d.name
    if renamed and get_by_name(db, d.project_id, fields["name"]) is not None:
        raise Conflict(f"dataset '{fields['name']}' already exists in this project")
    for k, v in fields.items():
        if v is not None:
            setattr(d, k, v)
    db.commit()
    db.refresh(d)
    return d


def soft_delete(db: Session, d: Dataset) -> None:
    d.deleted_at = datetime.now(UTC)
    db.commit()


# --- versions -----------------------------------------------------------------------------


def list_versions(db: Session, d: Dataset) -> list[DatasetVersion]:
    return list(
        db.scalars(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == d.id)
            .order_by(DatasetVersion.version)
        ).all()
    )


def latest_version(db: Session, d: Dataset) -> DatasetVersion | None:
    return db.scalar(
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == d.id)
        .order_by(DatasetVersion.version.desc())
        .limit(1)
    )


def get_version(db: Session, d: Dataset, version: int) -> DatasetVersion:
    v = db.scalar(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id == d.id, DatasetVersion.version == version
        )
    )
    if v is None:
        raise NotFound("dataset version not found")
    return v


def _lib_samples(records: list[dict[str, Any]]) -> list[LibSample]:
    """Validate with the library's model: derived ids, frozen content, duplicates, size."""
    try:
        samples = [LibSample.model_validate(r) for r in records]
    except (ValueError, TypeError) as err:
        raise Invalid(f"invalid sample: {err}") from err
    seen: dict[str, int] = {}
    for i, s in enumerate(samples):
        size = len(canonical(s.model_dump(mode="json")).encode())
        if size > MAX_SAMPLE_BYTES:
            raise Invalid(
                f"sample {s.id!r} at position {i} is {size} bytes; "
                f"the limit is {MAX_SAMPLE_BYTES} bytes of canonical JSON"
            )
        if s.id in seen:
            raise Invalid(
                f"duplicate sample id {s.id!r} at positions {seen[s.id]} and {i} "
                "(ids derive from input+expected; give explicit ids to keep both)"
            )
        seen[s.id] = i
    return samples


def content_hash_of(samples: list[LibSample]) -> str:
    return sha256([s.content() for s in samples])  # == library Dataset.content_hash


def _upsert_samples(db: Session, project_id: uuid.UUID, samples: list[LibSample]) -> list[Sample]:
    """One row per (project, content), race-safe (ON CONFLICT DO NOTHING, then re-select).

    `metadata` and `source` sit outside the content hash (the library's contract), so a
    re-push of a known case refreshes them: the latest push wins and every version that
    lists the row sees the refreshed annotation.
    """
    hashes = [sha256(s.content()) for s in samples]
    values = [
        {
            "id": uuid.uuid4(),
            "project_id": project_id,
            "sample_key": s.id,
            "content_hash": h,
            "input": s.input,
            "expected": s.expected,
            "metadata": dict(s.metadata),
            "tags": sorted(s.tags),
            "source": s.source.value,
        }
        for s, h in zip(samples, hashes, strict=True)
    ]
    db.execute(
        insert(Sample)
        .values(values)
        .on_conflict_do_nothing(index_elements=["project_id", "content_hash"])
    )
    by_hash = {
        row.content_hash: row
        for row in db.scalars(
            select(Sample).where(Sample.project_id == project_id, Sample.content_hash.in_(hashes))
        ).all()
    }
    rows: list[Sample] = []
    for s, h in zip(samples, hashes, strict=True):
        row = by_hash[h]
        if row.metadata_ != dict(s.metadata) or row.source != s.source.value:
            row.metadata_, row.source = dict(s.metadata), s.source.value
        rows.append(row)
    db.flush()
    return rows


def create_version(
    db: Session,
    *,
    dataset: Dataset,
    records: list[dict[str, Any]],
    note: str = "",
    created_by: User | None,
) -> tuple[DatasetVersion, bool]:
    """Snapshot `records` as the next version. Same content as the latest → (latest, False).

    The dataset row is locked FOR UPDATE for the transaction, so two concurrent pushes
    serialise: the second sees the first's version and returns it instead of racing into
    the (dataset_id, version) unique constraint.
    """
    samples = _lib_samples(records)
    digest = content_hash_of(samples)
    db.execute(select(Dataset.id).where(Dataset.id == dataset.id).with_for_update())
    latest = latest_version(db, dataset)
    if latest is not None and latest.content_hash == digest:
        db.rollback()  # release the lock; nothing to write
        return latest, False  # idempotent push: nothing changed
    rows = _upsert_samples(db, dataset.project_id, samples)
    version = DatasetVersion(
        dataset_id=dataset.id,
        version=(latest.version + 1) if latest else 1,
        content_hash=digest,
        sample_count=len(rows),
        note=note,
        created_by_user_id=created_by.id if created_by else None,
    )
    db.add(version)
    db.flush()
    db.add_all(
        DatasetVersionSample(dataset_version_id=version.id, sample_id=row.id, position=i)
        for i, row in enumerate(rows)
    )
    db.commit()
    db.refresh(version)
    return version, True


def version_samples(
    db: Session, version: DatasetVersion, *, offset: int = 0, limit: int = 200
) -> tuple[list[Sample], int]:
    base = (
        select(Sample)
        .join(DatasetVersionSample, DatasetVersionSample.sample_id == Sample.id)
        .where(DatasetVersionSample.dataset_version_id == version.id)
    )
    rows = list(
        db.scalars(base.order_by(DatasetVersionSample.position).offset(offset).limit(limit)).all()
    )
    return rows, version.sample_count
