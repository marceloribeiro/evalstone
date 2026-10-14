import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class Run(TimestampedModel):
    """One suite executed against one target, as the library reports it (`evalstone.run.Run`).

    `client_run_id` is the library's run id, unique per project, so a report pushed twice
    is stored once. `dataset_version_id` is linked when a version with the report's
    `dataset_hash` exists in the project; otherwise the name and hash are kept as text.
    """

    __tablename__ = "runs"
    __table_args__ = (
        Index(
            "uq_run_project_client_id_live",
            "project_id",
            "client_run_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        Index(  # one baseline per (project, suite), enforced by the database
            "uq_run_suite_baseline",
            "project_id",
            "suite",
            unique=True,
            postgresql_where="is_baseline AND deleted_at IS NULL",
        ),
        Index("ix_runs_project_suite_started", "project_id", "suite", "started_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    client_run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    suite: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id"), nullable=True
    )
    target: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    check_keys: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False, default="cli")
    baseline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id"), nullable=True
    )
    client_baseline_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # denormalised from summary for history queries
    pass_rate: Mapped[float] = mapped_column(Float, nullable=False)
    mean_score: Mapped[float] = mapped_column(Float, nullable=False)
    error_rate: Mapped[float] = mapped_column(Float, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    gate_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    gate_lines: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,  # None = ingest key
    )


class RunResult(TimestampedModel):
    """One sample x one check inside a run (`evalstone.run.Result`, flattened)."""

    __tablename__ = "run_results"
    __table_args__ = (
        Index("uq_result_run_sample_check", "run_id", "sample_key", "check_key", unique=True),
        Index("ix_results_run_check_passed", "run_id", "check_key", "passed"),
        Index("ix_results_check_judge_version", "check_key", "judge_version"),
        Index("ix_results_sample_output", "sample_key", "output_hash"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # the report's order
    sample_key: Mapped[str] = mapped_column(String(200), nullable=False)
    check_key: Mapped[str] = mapped_column(String(200), nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    input: Mapped[object | None] = mapped_column(JSONB, nullable=True)
    expected: Mapped[object | None] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # the library's output hash of `output` — what labels are keyed by
    output_hash: Mapped[str] = mapped_column(String(16), nullable=False)
    # stamped from score.raw for judge verdicts: rubric+scale+model hash, and the routed
    # `<provider>/<model>` (raw.judge_model, lib >= 0.2.3; NULL for older libraries)
    judge_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    judge_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    skipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw: Mapped[object | None] = mapped_column(JSONB, nullable=True)
