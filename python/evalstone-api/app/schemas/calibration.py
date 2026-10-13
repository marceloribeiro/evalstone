import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JudgeOut(BaseModel):
    check_key: str
    judge_version: str
    model: str | None
    results: int
    runs: int
    first_seen: datetime
    last_seen: datetime


class CalibrationIn(BaseModel):
    check_key: str = Field(min_length=1, max_length=200)
    judge_version: str | None = Field(default=None, min_length=16, max_length=16)
    label_check: str = Field(default="", max_length=200, description="'' = the overall grade")


class CalibrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    check_key: str
    judge_version: str
    label_check: str
    status: str
    error: str | None
    n: int
    agreement: float | None
    kappa: float | None
    mean_abs_error: float | None
    confusion: dict[str, Any]
    model: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime
