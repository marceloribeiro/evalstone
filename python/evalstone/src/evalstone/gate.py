"""Gates turn a run into a decision."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    as a fraction). Without a baseline the comparison is skipped, which suits a first
    run; ``require_baseline`` makes it mandatory instead, failing the gate when the
    baseline is missing, belongs to another suite, failed its own error threshold, or
    ran on a different dataset version or check set. ``max_error_rate`` defaults to 0:
    a judge outage fails the gate. Unknown keys are rejected, so a misspelt threshold
    fails loudly instead of being ignored.
    """

    model_config = ConfigDict(extra="forbid")

    min_pass_rate: float | None = Field(default=None, ge=0, le=1)
    min_mean_score: float | None = Field(default=None, ge=0, le=1)
    max_regression: float | None = Field(default=None, ge=0, le=1)
    max_cost_usd: float | None = Field(default=None, ge=0)
    max_error_rate: float = Field(default=0.0, ge=0, le=1)
    require_baseline: bool = False

    @model_validator(mode="after")
    def _baseline_needs_regression(self) -> Gate:
        if self.require_baseline and self.max_regression is None:
            raise ValueError("require_baseline needs max_regression (the comparison it requires)")
        return self

    def evaluate(self, run: Run, baseline: Run | None = None) -> GateReport:
        s = run.summary
        lines: list[str] = []
        failures: list[str] = []

        def rule(ok: bool, text: str) -> None:
            lines.append(("PASS " if ok else "FAIL ") + text)
            if not ok:
                failures.append(text)

        rule(s.results > 0, f"{s.results} results scored (a run with nothing scored never passes)")
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
            unpriced = _unpriced_calls(run)
            if unpriced:
                lines.append(
                    f"WARN {unpriced} result(s) from an unpriced model counted as $0 "
                    "(add it under `prices:` in evalstone.yaml)"
                )
        if self.max_regression is not None:
            if baseline is None:
                if self.require_baseline:
                    rule(False, "regression: no baseline run (require_baseline)")
                else:
                    lines.append("SKIP regression: no baseline run")
            else:
                if self.require_baseline:
                    # Each mismatch is its own FAIL line; a drop across a mismatch means nothing.
                    comparable = _comparable(run, baseline, self.max_error_rate, rule)
                else:
                    comparable = True
                    if baseline.dataset_hash != run.dataset_hash:
                        lines.append("WARN baseline ran on a different dataset version")
                if comparable:
                    drop = baseline.summary.pass_rate - s.pass_rate
                    rule(
                        drop <= self.max_regression,
                        f"pass rate dropped {drop:.1%} vs baseline (max {self.max_regression:.1%})",
                    )
        return GateReport(passed=not failures, checks=lines, failures=failures)


__all__ = ["Gate", "GateFailed", "GateReport"]


def _comparable(
    run: Run, baseline: Run, max_error_rate: float, rule: Callable[[bool, str], None]
) -> bool:
    """Under ``require_baseline``: fail (via ``rule``) every reason the baseline's pass
    rate cannot stand in for this run's; True when there is none."""
    reasons: list[str] = []
    b = baseline.summary
    if baseline.suite != run.suite:
        reasons.append(f"baseline is suite {baseline.suite!r}, this run is {run.suite!r}")
    if b.results == 0:
        reasons.append("baseline run scored no results")
    elif b.error_rate > max_error_rate:
        # e.g. recorded during a judge outage: its near-zero pass rate would hide any drop
        reasons.append(f"baseline error rate {b.error_rate:.1%} > {max_error_rate:.1%}")
    if baseline.dataset_hash != run.dataset_hash:
        reasons.append(
            f"baseline ran on dataset {baseline.dataset_hash[:12]}, "
            f"this run on {run.dataset_hash[:12]}"
        )
    if sorted(baseline.check_keys) != sorted(run.check_keys):
        reasons.append(
            f"baseline checks {sorted(baseline.check_keys)} differ from {sorted(run.check_keys)}"
        )
    for reason in reasons:
        rule(False, f"regression: {reason} (require_baseline)")
    return not reasons


def _unpriced_calls(run: Any) -> int:
    """Calls whose model is not in the price table: one per judge/comparison result
    flagged ``unpriced``, plus one per sample whose target call was (the output is
    shared by every check of that sample, so it is counted once)."""
    judged = 0
    for r in run.results:
        raw = r.score.raw
        if isinstance(raw, dict) and raw.get("unpriced"):
            judged += 1
    targets = 0
    for output in {r.sample_id: r.output for r in run.results}.values():
        meta = getattr(output, "metadata", None)
        if isinstance(meta, dict) and meta.get("unpriced"):
            targets += 1
    return judged + targets
