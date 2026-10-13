import uuid
from datetime import datetime

from evalstone.providers import ChatMessage
from pydantic import BaseModel, ConfigDict, Field

from app.services.judge_settings import MAX_BARE_MODEL, MAX_PROVIDER_NAME
from app.services.model_proxy import MAX_OUTPUT_TOKENS, Usage


class CompleteIn(BaseModel):
    """The library's `ChatRequest` minus the bare model, plus how to pick the model."""

    model: str | None = Field(
        default=None,
        max_length=MAX_PROVIDER_NAME + 1 + MAX_BARE_MODEL,
        description="<provider>/<model>",
    )
    check_key: str | None = Field(
        default=None, max_length=200, description="resolve the model from the judge settings"
    )
    system: str | None = None
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)
    max_tokens: int = Field(default=1024, ge=1, le=MAX_OUTPUT_TOKENS)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class CompleteOut(BaseModel):
    """The library's `ChatResponse` without `raw`."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    latency_ms: float
    stop_reason: str | None


class ModelCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_name: str
    model: str
    check_key: str | None
    ok: bool
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    latency_ms: float
    error: str | None
    caller_user_id: uuid.UUID | None
    created_at: datetime


class ModelCallPage(BaseModel):
    items: list[ModelCallOut]
    total: int
    offset: int
    limit: int


UsageOut = Usage
