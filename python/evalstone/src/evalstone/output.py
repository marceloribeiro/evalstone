"""What a target produced for one sample."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from evalstone._json import dumps


class Output(BaseModel):
    """The target's output plus the facts about producing it that checks may need."""

    model_config = ConfigDict(frozen=True)

    value: Any
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @property
    def text(self) -> str:
        """A string view of ``value`` for text checks: strings as-is, everything else as JSON."""
        if isinstance(self.value, str):
            return self.value
        if self.value is None:
            return ""
        return dumps(self.value, sort_keys=True)

    @classmethod
    def failed(cls, error: str, **kwargs: Any) -> Output:
        kwargs.setdefault("value", None)
        return cls(error=error, **kwargs)
