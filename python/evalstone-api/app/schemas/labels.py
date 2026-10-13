import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScoreIn(BaseModel):
    """The library's `evalstone.score.Score`."""

    value: float = Field(ge=0.0, le=1.0)
    passed: bool
    reason: str = ""
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    error: str | None = None
    raw: Any = None
    skipped: bool = False


class CachePutIn(BaseModel):
    score: ScoreIn
    judge_version: str | None = Field(default=None, max_length=16)


class CacheEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cache_key: str
    judge_version: str | None
    score: dict[str, Any]
    hits: int
    last_hit_at: datetime | None
    created_at: datetime


class CacheLookupIn(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=1000)


class LabelIn(BaseModel):
    """The library's `evalstone.checks.human.Label` wire shape (a labels.jsonl line)."""

    sample_id: str = Field(min_length=1, max_length=200)
    output_hash: str = Field(min_length=1, max_length=16)
    value: float = Field(ge=0.0, le=1.0)
    passed: bool
    notes: str = Field(default="", max_length=5000)
    check: str | None = Field(default=None, max_length=200)
    labeler: str = Field(default="", max_length=200)
    created_at: datetime | None = None
    raw: Any = None


class LabelsPushIn(BaseModel):
    labels: list[LabelIn] = Field(max_length=5000)


class LabelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sample_key: str
    output_hash: str
    check_key: str
    value: float
    passed: bool
    notes: str
    labeler: str
    labeler_user_id: uuid.UUID | None
    labeled_at: datetime
    raw: Any


class LabelPage(BaseModel):
    items: list[LabelOut]
    total: int
    offset: int
    limit: int
