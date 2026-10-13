"""Scores and the Check protocol.

A ``Check`` evaluates one ``Output`` for one ``Sample`` and returns a ``Score``:
``value`` in 0..1, ``passed``, a ``reason``, what it cost, and ``error`` when it
could not score. **An error is never a pass** — ``passed`` is forced to
``False`` whenever ``error`` is set, so a judge outage cannot turn a suite green.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from evalstone.dataset import Sample
    from evalstone.output import Output


class CheckKind(StrEnum):
    DETERMINISTIC = "deterministic"
    JUDGE = "judge"
    HUMAN = "human"
    COMPARISON = "comparison"
    TRAJECTORY = "trajectory"
    RAG = "rag"
    SAFETY = "safety"


class Score(BaseModel):
    """One check's verdict on one output."""

    model_config = ConfigDict(frozen=True)

    value: float = Field(ge=0.0, le=1.0)
    passed: bool
    reason: str = ""
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    error: str | None = None
    raw: Any = None

    @model_validator(mode="after")
    def _error_never_passes(self) -> Score:
        if self.error is not None and self.passed:
            object.__setattr__(self, "passed", False)
        return self

    @classmethod
    def ok(cls, reason: str = "", *, value: float = 1.0, **kw: Any) -> Score:
        kw.setdefault("passed", True)
        return cls(value=value, reason=reason, **kw)

    @classmethod
    def fail(cls, reason: str = "", *, value: float = 0.0, **kw: Any) -> Score:
        kw.setdefault("passed", False)
        return cls(value=value, reason=reason, **kw)

    @classmethod
    def errored(cls, error: str, **kw: Any) -> Score:
        """The check could not score this output. Counted separately, never a pass.

        ``reason`` defaults to the error text; pass your own to keep a short error
        code and a longer explanation apart.
        """
        kw.setdefault("reason", error)
        kw.setdefault("value", 0.0)
        return cls(passed=False, error=error, **kw)

    @classmethod
    def from_bool(cls, ok: bool, reason: str = "") -> Score:
        return cls.ok(reason) if ok else cls.fail(reason)

    @classmethod
    def from_value(cls, value: float, *, threshold: float = 1.0, reason: str = "") -> Score:
        """A graded score that passes at or above ``threshold``."""
        return cls(value=value, passed=value >= threshold, reason=reason)


class ScoreCache(Protocol):
    """Where judge verdicts are remembered, keyed by content hash."""

    def get(self, key: str) -> Score | None: ...

    def set(self, key: str, score: Score) -> None: ...


class MemoryCache:
    """An in-process ``ScoreCache``. The center-backed cache arrives with Phase 3."""

    def __init__(self) -> None:
        self._data: dict[str, Score] = {}

    def get(self, key: str) -> Score | None:
        return self._data.get(key)

    def set(self, key: str, score: Score) -> None:
        self._data[key] = score

    def __len__(self) -> int:
        return len(self._data)


class Context(BaseModel):
    """Run-wide facts a check may need: model access (``providers``), the judge
    cache, and free-form ``extra``."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str | None = None
    providers: Any = None  # evalstone.providers.Providers, or None when no model access
    cache: Any = Field(default_factory=MemoryCache)  # ScoreCache; set None to disable
    extra: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class Check(Protocol):
    """Anything with a ``key``, a ``kind`` and an ``evaluate`` method is a check."""

    key: str
    kind: CheckKind

    def evaluate(self, sample: Sample, output: Output, ctx: Context) -> Score: ...
