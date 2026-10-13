import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel

CALIBRATION_STATUSES = ("queued", "running", "done", "failed")


class Calibration(TimestampedModel):
    """How well one judge version agrees with the humans, on the outputs both have graded.

    A judge version is the library's 16-hex `judge_version` (rubric + scale + model), carried
    in every judge result's `raw`. The label set is the project's labels under `label_check`
    ('' = the overall grade). Metrics are over the (sample, output) pairs present in both.
    """

    __tablename__ = "calibrations"
    __table_args__ = (Index("ix_calibrations_project_created", "project_id", "created_at"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    check_key: Mapped[str] = mapped_column(String(200), nullable=False)
    judge_version: Mapped[str] = mapped_column(String(16), nullable=False)
    label_check: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    n: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agreement: Mapped[float | None] = mapped_column(Float, nullable=True)
    kappa: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_abs_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    confusion: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
