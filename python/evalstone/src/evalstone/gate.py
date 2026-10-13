"""Gates turn a run into a decision."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from evalstone.run import Run


class GateFailed(Exception):
    """Raised by ``Run.gate()`` when the gate does not pass."""

    def __init__(self, report: GateReport):
        self.report = report
        super().__init__("; ".join(report.failures) or "gate failed")


class GateReport(BaseModel):
    passed: bool
    checks: list[str] = Field(default_factory=list)  # human-readable lines, pass and fail
    failures: list[str] = Field(default_factory=list)


class Gate(BaseModel):
    """Thresholds a run must meet. ``None`` disables a threshold.

    ``max_regression`` compares against a baseline run (pass-rate drop allowed,
    as a fraction). ``max_error_rate`` defaults to 0: a judge outage fails the gate.
    """

    min_pass_rate: float | None = Field(default=None, ge=0, le=1)
    min_mean_score: float | None = Field(default=None, ge=0, le=1)
    max_regression: float | None = Field(default=None, ge=0, le=1)
    max_cost_usd: float | None = Field(default=None, ge=0)
    max_error_rate: float = Field(default=0.0, ge=0, le=1)

    def evaluate(self, run: Run, baseline: Run | None = None) -> GateReport:
        s = run.summary
        lines: list[str] = []
        failures: list[str] = []

        def rule(ok: bool, text: str) -> None:
            lines.append(("PASS " if ok else "FAIL ") + text)
            if not ok:
                failures.append(text)

        rule(
            s.error_rate <= self.max_error_rate,
            f"error rate {s.error_rate:.1%} ≤ {self.max_error_rate:.1%}",
        )
        if self.min_pass_rate is not None:
            rule(
                s.pass_rate >= self.min_pass_rate,
                f"pass rate {s.pass_rate:.1%} ≥ {self.min_pass_rate:.1%}",
            )
        if self.min_mean_score is not None:
            rule(
                s.mean_score >= self.min_mean_score,
                f"mean score {s.mean_score:.3f} ≥ {self.min_mean_score:.3f}",
            )
        if self.max_cost_usd is not None:
            rule(
                s.cost_usd <= self.max_cost_usd,
                f"cost ${s.cost_usd:.4f} ≤ ${self.max_cost_usd:.4f}",
            )
        if self.max_regression is not None:
            if baseline is None:
                lines.append("SKIP regression: no baseline run")
            else:
                if baseline.dataset_hash != run.dataset_hash:
                    lines.append("WARN baseline ran on a different dataset version")
                drop = baseline.summary.pass_rate - s.pass_rate
                rule(
                    drop <= self.max_regression,
                    f"pass rate dropped {drop:.1%} vs baseline (max {self.max_regression:.1%})",
                )
        return GateReport(passed=not failures, checks=lines, failures=failures)


__all__ = ["Gate", "GateFailed", "GateReport"]
