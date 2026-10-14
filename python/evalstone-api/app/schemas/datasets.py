import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.datasets import MAX_SAMPLES_PER_VERSION


def _clean_tags(tags: list[str] | None) -> list[str] | None:
    """Trimmed, non-empty, first occurrence wins — the client renders tags by value."""
    if tags is None:
        return None
    seen: dict[str, None] = {}
    for t in tags:
        t = t.strip()
        if t:
            seen.setdefault(t, None)
    return list(seen)


class DatasetIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=50)

    _tags = field_validator("tags")(_clean_tags)


class DatasetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    tags: list[str] | None = Field(default=None, max_length=50)

    _tags = field_validator("tags")(_clean_tags)


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str
    tags: list[str]
    created_at: datetime


class SampleIn(BaseModel):
    """The library's `Sample` wire shape (`evalstone.dataset.Sample`)."""

    id: str = Field(default="", max_length=200)
    input: Any
    expected: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=50)
    source: Literal["manual", "harvested", "synthetic"] = "manual"


class VersionIn(BaseModel):
    samples: list[SampleIn] = Field(min_length=1, max_length=MAX_SAMPLES_PER_VERSION)
    note: str = Field(default="", max_length=2000)


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    version: int
    content_hash: str
    sample_count: int
    note: str
    created_by_user_id: uuid.UUID | None
    created_at: datetime


class SampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sample_key: str
    content_hash: str
    input: Any
    expected: Any | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    tags: list[str]
    source: str


class SamplePage(BaseModel):
    items: list[SampleOut]
    total: int
    offset: int
    limit: int
