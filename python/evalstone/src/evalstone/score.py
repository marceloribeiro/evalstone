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
        return cls(value=value, passed=True, reason=reason, **kw)

    @classmethod
    def fail(cls, reason: str = "", *, value: float = 0.0, **kw: Any) -> Score:
        return cls(value=value, passed=False, reason=reason, **kw)

    @classmethod
    def errored(cls, error: str, **kw: Any) -> Score:
        """The check could not score this output. Counted separately, never a pass."""
        return cls(value=0.0, passed=False, error=error, reason=error, **kw)

    @classmethod
    def from_bool(cls, ok: bool, reason: str = "") -> Score:
        return cls.ok(reason) if ok else cls.fail(reason)

    @classmethod
    def from_value(cls, value: float, *, threshold: float = 1.0, reason: str = "") -> Score:
        """A graded score that passes at or above ``threshold``."""
        return cls(value=value, passed=value >= threshold, reason=reason)


class Context(BaseModel):
    """Run-wide facts a check may need (configuration, model access, caches).

    Kept deliberately small in this slice; judges extend it in a later PR.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class Check(Protocol):
    """Anything with a ``key``, a ``kind`` and an ``evaluate`` method is a check."""

    key: str
    kind: CheckKind

    def evaluate(self, sample: Sample, output: Output, ctx: Context) -> Score: ...
