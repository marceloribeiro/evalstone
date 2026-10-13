"""Datasets, immutable versions and content-addressed samples.

Hashes are computed with the library's own code (`evalstone.dataset.Sample`,
`evalstone._json.sha256`) so a version pushed from the CLI has the same `content_hash`
the center stores, and the same sample ids.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from evalstone._json import sha256
from evalstone.dataset import Sample as LibSample
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import Conflict, Invalid, NotFound
from app.models import Dataset, DatasetVersion, DatasetVersionSample, Project, Sample, User

MAX_SAMPLES_PER_VERSION = 5000


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


def get_by_name(db: Session, project: Project, name: str) -> Dataset | None:
    return db.scalar(
        select(Dataset).where(
            Dataset.project_id == project.id, Dataset.name == name, Dataset.deleted_at.is_(None)
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
    if get_by_name(db, project, name) is not None:
        raise Conflict(f"dataset '{name}' already exists in this project")
    d = Dataset(project_id=project.id, name=name, description=description, tags=list(tags or []))
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def update(db: Session, d: Dataset, **fields) -> Dataset:
    if fields.get("name") and fields["name"] != d.name:
        project = db.get(Project, d.project_id)
        if get_by_name(db, project, fields["name"]) is not None:
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
    """Validate with the library's model: derived ids, frozen content, duplicate detection."""
    if len(records) > MAX_SAMPLES_PER_VERSION:
        raise Invalid(f"at most {MAX_SAMPLES_PER_VERSION} samples per version")
    if not records:
        raise Invalid("a version needs at least one sample")
    try:
        samples = [LibSample.model_validate(r) for r in records]
    except (ValueError, TypeError) as err:
        raise Invalid(f"invalid sample: {err}") from err
    seen: dict[str, int] = {}
    for i, s in enumerate(samples):
        if s.id in seen:
            raise Invalid(
                f"duplicate sample id {s.id!r} at positions {seen[s.id]} and {i} "
                "(ids derive from input+expected; give explicit ids to keep both)"
            )
        seen[s.id] = i
    return samples


def content_hash_of(samples: list[LibSample]) -> str:
    return sha256([s.content() for s in samples])  # == library Dataset.content_hash


def _upsert_samples(db: Session, project: Project, samples: list[LibSample]) -> list[Sample]:
    """One row per (project, content); metadata/source of an existing row are left as they are."""
    hashes = [sha256(s.content()) for s in samples]
    existing = {
        row.content_hash: row
        for row in db.scalars(
            select(Sample).where(Sample.project_id == project.id, Sample.content_hash.in_(hashes))
        ).all()
    }
    rows: list[Sample] = []
    for s, h in zip(samples, hashes, strict=True):
        row = existing.get(h)
        if row is None:
            row = Sample(
                project_id=project.id,
                sample_key=s.id,
                content_hash=h,
                input=s.input,
                expected=s.expected,
                metadata_=dict(s.metadata),
                tags=sorted(s.tags),
                source=s.source.value,
            )
            db.add(row)
            existing[h] = row
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
    """Snapshot `records` as the next version. Same content as the latest → (latest, False)."""
    samples = _lib_samples(records)
    digest = content_hash_of(samples)
    latest = latest_version(db, dataset)
    if latest is not None and latest.content_hash == digest:
        return latest, False  # idempotent push: nothing changed
    project = db.get(Project, dataset.project_id)
    rows = _upsert_samples(db, project, samples)
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


def project_sample_count(db: Session, project: Project) -> int:
    return db.scalar(select(func.count()).where(Sample.project_id == project.id))
