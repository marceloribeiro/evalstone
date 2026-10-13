import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class QueueIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["grade", "compare", "verify"]
    source: dict[str, Any] = Field(
        description="grade: {run_id, check_key?, failed_only?} · compare: {run_a, run_b} · "
        "verify: {dataset_id, version}"
    )
    instructions: str = Field(default="", max_length=5000)
    check_key: str = Field(default="", max_length=200, description="'' = overall label")
    scale: int = Field(default=5, ge=2, le=10)
    due_at: datetime | None = None


class QueueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    kind: str
    instructions: str
    check_key: str
    scale: int
    source: dict[str, Any]
    status: str
    due_at: datetime | None
    task_count: int
    created_by_user_id: uuid.UUID | None
    created_at: datetime


class QueueStatusIn(BaseModel):
    status: Literal["open", "closed"]


class ProgressOut(BaseModel):
    total: int
    pending: int
    claimed: int
    done: int
    skipped: int


class AssignIn(BaseModel):
    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class UnassignIn(BaseModel):
    user_ids: list[uuid.UUID] | None = Field(
        default=None, max_length=50, description="null = everyone"
    )


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    queue_id: uuid.UUID
    position: int
    sample_key: str
    output_hash: str
    payload: dict[str, Any]
    status: str
    assignee_user_id: uuid.UUID | None
    claimed_at: datetime | None
    done_at: datetime | None
    label_id: uuid.UUID | None


class TaskPage(BaseModel):
    items: list[TaskOut]
    total: int
    offset: int
    limit: int


class AnswerIn(BaseModel):
    grade: int | None = Field(default=None, ge=1, le=10, description="1..scale (grade/verify)")
    passed: bool | None = None
    winner: Literal["a", "b", "tie"] | None = Field(default=None, description="compare tasks")
    notes: str = Field(default="", max_length=5000)


class SkipIn(BaseModel):
    reason: str = Field(default="", max_length=1000)
