import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    client_run_id: str
    suite: str
    dataset_name: str
    dataset_hash: str
    dataset_version_id: uuid.UUID | None
    target: dict[str, Any]
    check_keys: list[str]
    git_sha: str | None
    trigger: str
    baseline_run_id: uuid.UUID | None
    client_baseline_run_id: str | None
    started_at: datetime
    finished_at: datetime
    summary: dict[str, Any]
    pass_rate: float
    mean_score: float
    error_rate: float
    cost_usd: float
    duration_ms: float
    result_count: int
    gate_passed: bool | None
    gate_lines: list[str]
    is_baseline: bool
    created_by_user_id: uuid.UUID | None
    created_at: datetime


class SuiteOut(BaseModel):
    """One suite of the project: how many runs it has and which one is its baseline."""

    suite: str
    runs: int
    last_started_at: datetime
    baseline_run_id: uuid.UUID | None


class RunPage(BaseModel):
    items: list[RunOut]
    total: int
    offset: int
    limit: int


class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sample_key: str
    check_key: str
    tags: list[str]
    input: Any
    expected: Any
    output: dict[str, Any]
    score: float
    passed: bool
    reason: str
    cost_usd: float
    latency_ms: float
    error: str | None
    skipped: bool


class ResultPage(BaseModel):
    items: list[ResultOut]
    total: int
    offset: int
    limit: int


class BaselineIn(BaseModel):
    is_baseline: bool = Field(default=True)
