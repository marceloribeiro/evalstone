import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel

QUEUE_KINDS = ("grade", "compare", "verify")
TASK_STATUSES = ("pending", "done", "skipped")


class LabelQueue(TimestampedModel):
    """A batch of human work: grade a run's outputs, compare two runs, or verify a dataset."""

    __tablename__ = "label_queues"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    check_key: Mapped[str] = mapped_column(String(200), nullable=False, default="")  # '' = overall
    scale: Mapped[int] = mapped_column(Integer, nullable=False, default=5)  # 2 = pass/fail
    source: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # run/version ids
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    task_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class LabelTask(TimestampedModel):
    """One item for a person: the sample, the output(s) to judge, and where the label went."""

    __tablename__ = "label_tasks"
    __table_args__ = (
        UniqueConstraint("queue_id", "position", name="uq_task_queue_position"),
        Index("ix_tasks_queue_status_assignee", "queue_id", "status", "assignee_user_id"),
    )

    queue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("label_queues.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_key: Mapped[str] = mapped_column(String(200), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(16), nullable=False)  # of output A
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)  # input, expected, output(s)…
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    label_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("labels.id"), nullable=True
    )
