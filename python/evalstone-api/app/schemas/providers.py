import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

Adapter = Literal["openai", "anthropic", "gemini"]


class ProviderIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    adapter: Adapter
    api_key: str | None = Field(default=None, max_length=1000)
    base_url: str | None = Field(default=None, max_length=500)
    headers: dict[str, str] = Field(default_factory=dict)
    prices: dict[str, list[float]] = Field(default_factory=dict)
    timeout_s: float = Field(default=60.0, gt=0, le=600)
    max_tokens_param: Literal["max_tokens", "max_completion_tokens"] | None = None


class ProviderUpdate(BaseModel):
    api_key: str | None = Field(default=None, max_length=1000)  # "" clears, absent keeps
    base_url: str | None = Field(default=None, max_length=500)
    headers: dict[str, str] | None = None
    prices: dict[str, list[float]] | None = None
    timeout_s: float | None = Field(default=None, gt=0, le=600)
    max_tokens_param: Literal["max_tokens", "max_completion_tokens"] | None = None


class ProviderOut(BaseModel):
    """Never carries the key: `has_api_key` + `key_last4` are all a client learns."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    adapter: Adapter
    base_url: str | None
    headers: dict[str, str]
    prices: dict[str, list[float]]
    timeout_s: float
    max_tokens_param: str | None
    key_last4: str | None
    verified_ok: bool | None
    last_verified_at: datetime | None
    last_error: str | None
    created_at: datetime

    @computed_field
    @property
    def has_api_key(self) -> bool:
        return self.key_last4 is not None


class ProviderTestIn(BaseModel):
    model: str = Field(
        min_length=1, max_length=150, description="bare model id, no provider prefix"
    )


class ProviderTestOut(BaseModel):
    ok: bool
    model: str
    latency_ms: float | None
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    error: str | None


class JudgeSettingsIn(BaseModel):
    default_model: str | None = Field(default=None, max_length=200)
    overrides: dict[str, str] = Field(default_factory=dict)


class JudgeSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: uuid.UUID
    default_model: str | None
    overrides: dict[str, str]
