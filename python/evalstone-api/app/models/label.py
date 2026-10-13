import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class JudgeCacheEntry(TimestampedModel):
    """A judge's raw verdict under the library's content key: `sha256({"j": version, "u": prompt})`.

    The library's `ScoreCache` protocol is get/set by key; the center is the cross-run,
    cross-machine cache. `score` is the library's `Score` JSON.
    """

    __tablename__ = "judge_cache"
    __table_args__ = (UniqueConstraint("project_id", "cache_key", name="uq_judge_cache_key"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,  # uq_judge_cache_key leads
    )
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    judge_version: Mapped[str | None] = mapped_column(String(16), nullable=True)  # for calibration
    score: Mapped[dict] = mapped_column(JSONB, nullable=False)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Label(TimestampedModel):
    """A human verdict on one (sample, output) pair — the library's `evalstone.checks.human.Label`.

    Keyed by sample id + a hash of the output text (+ the check it grades, '' = overall), so a
    label never silently applies to a changed answer. A re-push replaces (later wins).
    """

    __tablename__ = "labels"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "sample_key", "output_hash", "check_key", name="uq_label_sample_output"
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,  # uq_label_sample_output leads
    )
    sample_key: Mapped[str] = mapped_column(String(200), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(16), nullable=False)
    check_key: Mapped[str] = mapped_column(String(200), nullable=False, default="")  # '' = overall
    value: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    labeler: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    labeler_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    labeled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw: Mapped[object | None] = mapped_column(JSONB, nullable=True)
