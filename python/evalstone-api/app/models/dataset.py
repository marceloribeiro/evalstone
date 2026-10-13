import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel

EMBEDDING_DIM = 1536  # reserved for harvest/dedup (slice 9); nothing writes it yet


class Dataset(TimestampedModel):
    """A named collection of cases inside a project; its content lives in immutable versions."""

    __tablename__ = "datasets"
    __table_args__ = (
        Index(
            "uq_dataset_project_name_live",
            "project_id",
            "name",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class DatasetVersion(TimestampedModel):
    """Immutable snapshot; `content_hash` equals the library's `Dataset.content_hash`."""

    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version", name="uq_dataset_version_number"),)

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,  # None = pushed with an ingest key
    )


class Sample(TimestampedModel):
    """One case, stored once per project by content and shared by every version that lists it.

    `sample_key` is the library's `Sample.id` (explicit or derived from input+expected);
    `content_hash` covers id, input, expected and sorted tags exactly like `Sample.content()`.
    `metadata` and `source` sit outside the hash, as in the library.
    """

    __tablename__ = "samples"
    __table_args__ = (
        UniqueConstraint("project_id", "content_hash", name="uq_sample_project_content"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    sample_key: Mapped[str] = mapped_column(String(200), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input: Mapped[object] = mapped_column(JSONB, nullable=False)
    expected: Mapped[object | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)


class DatasetVersionSample(TimestampedModel):
    """Ordered membership of a sample in a version (position = the library's list order)."""

    __tablename__ = "dataset_version_samples"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "position", name="uq_version_position"),
        UniqueConstraint("dataset_version_id", "sample_id", name="uq_version_sample"),
    )

    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id"), nullable=False, index=True
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("samples.id"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
