import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel

MONITOR_STATUSES = ("active", "paused")


class Trace(TimestampedModel):
    """One production interaction pushed with the project's ingest key: input, output, context."""

    __tablename__ = "traces"
    __table_args__ = (
        Index(
            "uq_trace_project_client_id_live",
            "project_id",
            "client_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        Index("ix_traces_project_occurred", "project_id", "occurred_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(String(128), nullable=False)  # the caller's id
    input: Mapped[object] = mapped_column(JSONB, nullable=False)
    output: Mapped[object | None] = mapped_column(JSONB, nullable=True)
    output_hash: Mapped[str] = mapped_column(String(16), nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # by a user
    # the bucket a monitor samples by: a stable 0..1 number derived from the trace's id
    sample_bucket: Mapped[float] = mapped_column(Float, nullable=False)


class Monitor(TimestampedModel):
    """A standing check over sampled traffic with a windowed alert policy."""

    __tablename__ = "monitors"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    check_keys: Mapped[list] = mapped_column(JSONB, nullable=False)  # org catalog keys
    sample_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.1)
    # {"metric": "pass_rate", "threshold": 0.9, "window_minutes": 60, "min_n": 20}
    alert_policy: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")
    last_scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class TraceScore(TimestampedModel):
    """One monitor's verdict on one trace for one check (the library's Score, flattened)."""

    __tablename__ = "trace_scores"
    __table_args__ = (
        Index("uq_trace_score", "monitor_id", "trace_id", "check_key", unique=True),
        Index("ix_trace_scores_monitor_scored", "monitor_id", "scored_at"),
    )

    monitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitors.id"), nullable=False
    )
    trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("traces.id"), nullable=False, index=True
    )
    check_key: Mapped[str] = mapped_column(String(200), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # errors retry
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Alert(TimestampedModel):
    """A monitor breach for one window; one open alert per monitor until it recovers."""

    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_monitor_opened", "monitor_id", "opened_at"),)

    monitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitors.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    metric: Mapped[str] = mapped_column(String(30), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    n: Mapped[int] = mapped_column(Integer, nullable=False)
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notify_error: Mapped[str | None] = mapped_column(Text, nullable=True)
