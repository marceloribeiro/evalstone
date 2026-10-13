import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.monitoring import MAX_TRACES_PER_PUSH


class TraceIn(BaseModel):
    id: str | None = Field(default=None, max_length=128, description="your id; retries dedupe")
    input: Any
    output: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=50)
    model: str | None = Field(default=None, max_length=200)
    latency_ms: float | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    occurred_at: datetime | None = None


class TracesPushIn(BaseModel):
    traces: list[TraceIn] = Field(min_length=1, max_length=MAX_TRACES_PER_PUSH)


class TraceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: str
    input: Any
    output: Any
    output_hash: str
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    tags: list[str]
    model: str | None
    latency_ms: float | None
    cost_usd: float | None
    occurred_at: datetime
    flagged: bool
    sample_bucket: float


class TracePage(BaseModel):
    items: list[TraceOut]
    total: int
    offset: int
    limit: int


class FlagIn(BaseModel):
    flagged: bool = True


class AlertPolicyIn(BaseModel):
    metric: Literal["pass_rate", "mean_score"] = "pass_rate"
    threshold: float = Field(ge=0.0, le=1.0)
    window_minutes: int = Field(default=60, ge=1, le=10080)
    min_n: int = Field(default=20, ge=1)


class MonitorIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    check_keys: list[str] = Field(min_length=1, max_length=20)
    sample_rate: float = Field(default=0.1, gt=0.0, le=1.0)
    alert_policy: AlertPolicyIn
    webhook_url: str | None = Field(default=None, max_length=500)


class MonitorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    check_keys: list[str] | None = Field(default=None, min_length=1, max_length=20)
    sample_rate: float | None = Field(default=None, gt=0.0, le=1.0)
    alert_policy: AlertPolicyIn | None = None
    webhook_url: str | None = Field(default=None, max_length=500)
    status: Literal["active", "paused"] | None = None


class MonitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    check_keys: list[str]
    sample_rate: float
    alert_policy: dict[str, Any]
    webhook_url: str | None
    status: str
    last_scored_at: datetime | None
    last_error: str | None
    created_at: datetime


class WindowOut(BaseModel):
    n: int
    pass_rate: float | None
    mean_score: float | None
    window_minutes: int


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    monitor_id: uuid.UUID
    metric: str
    value: float
    threshold: float
    n: int
    window_minutes: int
    opened_at: datetime
    resolved_at: datetime | None
    notified_at: datetime | None
    notify_error: str | None
