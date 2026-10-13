import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ParamOut(BaseModel):
    name: str
    required: bool
    default: Any
    annotation: str


class BuiltinOut(BaseModel):
    type: str
    kind: str
    params: list[ParamOut]
    summary: str
    library_version: str


class CheckIn(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)
    description: str = Field(default="", max_length=5000)


class CheckUpdate(BaseModel):
    type: str | None = Field(default=None, min_length=1, max_length=100)
    params: dict[str, Any] | None = None
    description: str | None = Field(default=None, max_length=5000)
    note: str = Field(default="", max_length=2000)


class CheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    key: str
    type: str
    kind: str
    params: dict[str, Any]
    description: str
    current_version: int
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class CheckVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    type: str
    params: dict[str, Any]
    content_hash: str
    note: str
    created_by_user_id: uuid.UUID | None
    created_at: datetime
