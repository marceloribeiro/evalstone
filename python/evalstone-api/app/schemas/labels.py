import uuid
from datetime import datetime
from typing import Any

from evalstone.checks.human import Label as LibLabel
from evalstone.score import Score
from pydantic import BaseModel, ConfigDict, Field

from app.services.judge_cache import MAX_LOOKUP_KEYS
from app.services.labels import MAX_LABELS_PER_PUSH


class CachePutIn(BaseModel):
    score: Score  # the library's evalstone.score.Score, verbatim
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
    keys: list[str] = Field(min_length=1, max_length=MAX_LOOKUP_KEYS)


class LabelsPushIn(BaseModel):
    labels: list[LibLabel] = Field(max_length=MAX_LABELS_PER_PUSH)  # labels.jsonl lines


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
