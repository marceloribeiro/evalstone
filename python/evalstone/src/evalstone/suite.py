"""A suite: ordered checks x a dataset, run against a target, judged by a gate."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterable
from typing import Any

from evalstone._git import head_sha
from evalstone.checks import registry
from evalstone.dataset import Dataset
from evalstone.gate import Gate, GateFailed, GateReport
from evalstone.output import Output
from evalstone.run import Result, Run, summarise
from evalstone.score import Check, CheckKind, Context, Score
from evalstone.target import CallableTarget, Target

# Checks that cost nothing to run: sorted before the model-backed ones (judge, comparison).
_CHEAP = {CheckKind.DETERMINISTIC, CheckKind.TRAJECTORY, CheckKind.SAFETY, CheckKind.HUMAN}
# Contracts: a failure here short-circuits the judges. A human label is a quality verdict,
# not a contract — the judge still runs, so judge/human agreement stays measurable.
_CONTRACTS = {CheckKind.DETERMINISTIC, CheckKind.TRAJECTORY, CheckKind.SAFETY}


class Suite:
    def __init__(
        self,
        name: str,
        *,
        dataset: Dataset,
        checks: Iterable[Check | str],
        gate: Gate | None = None,
        cheap_first: bool = True,
        short_circuit: bool = False,
    ) -> None:
        self.name = name
        self.dataset = dataset
        resolved = [registry.get(c) if isinstance(c, str) else c for c in checks]
        if not resolved:
            raise ValueError("a suite needs at least one check")
        keys = [c.key for c in resolved]
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        if dupes:
            raise ValueError(f"duplicate check keys in suite {name!r}: {dupes}")
        if cheap_first:
            resolved.sort(key=lambda c: 0 if c.kind in _CHEAP else 1)
        self.checks: list[Check] = resolved
        self.gate = gate
        self.short_circuit = short_circuit

    @property
    def check_keys(self) -> list[str]:
        return [c.key for c in self.checks]

    def run(
        self,
        target: Target | Callable[[Any], Any],
        *,
        baseline: Run | None = None,
        trigger: str = "cli",
        ctx: Context | None = None,
        on_sample: Callable[[int, int], None] | None = None,
    ) -> Run:
        """Produce an output per sample, score it with every check, summarise, gate."""
        tgt = target if isinstance(target, Target) else CallableTarget(target)
        started = Run.now()
        clock = time.perf_counter()
        results: list[Result] = []
        total = len(self.dataset)
        run_id = uuid.uuid4().hex[:12]
        run_ctx = (ctx or Context()).model_copy(update={"run_id": run_id})
        for i, sample in enumerate(self.dataset, start=1):
            # One sample never takes the run down: the invariant is enforced here, not
            # left to every Target / Check implementation.
            try:
                output = tgt.produce(sample)
            except Exception as exc:
                output = Output.failed(f"{type(exc).__name__}: {exc}")
            contract_failed: str | None = None  # the first cheap check that failed this sample
            for chk in self.checks:
                if output.error is not None:
                    score = Score.errored(f"target: {output.error}")
                elif self.short_circuit and contract_failed and chk.kind not in _CHEAP:
                    # a paid judge call is not spent on an output that already failed
                    score = Score.skip(f"skipped: {contract_failed} failed this output")
                else:
                    try:
                        score = chk.evaluate(sample, output, run_ctx)
                    except Exception as exc:
                        score = Score.errored(f"{type(exc).__name__}: {exc}")
                    if chk.kind in _CONTRACTS and not score.passed and score.error is None:
                        contract_failed = contract_failed or chk.key
                results.append(
                    Result(
                        sample_id=sample.id,
                        check_key=chk.key,
                        tags=sample.tags,
                        input=sample.input,
                        expected=sample.expected,
                        output=output,
                        score=score,
                    )
                )
            if on_sample:
                on_sample(i, total)
        duration = (time.perf_counter() - clock) * 1000
        run = Run(
            id=run_id,
            suite=self.name,
            dataset=self.dataset.name,
            dataset_hash=self.dataset.content_hash,
            target=tgt.describe(),
            check_keys=self.check_keys,
            git_sha=head_sha(),
            trigger=trigger,
            baseline_run_id=baseline.id if baseline else None,
            started_at=started,
            finished_at=Run.now(),
            results=results,
            summary=summarise(
                results, samples=total, checks=len(self.checks), duration_ms=duration
            ),
        )
        if self.gate is not None:
            report = self.gate.evaluate(run, baseline)
            run.gate_passed = report.passed
            run.gate_lines = report.checks
        return run

    def gate_report(self, run: Run, baseline: Run | None = None) -> GateReport:
        if self.gate is None:
            return GateReport(passed=True, checks=["SKIP no gate configured"])
        return self.gate.evaluate(run, baseline)

    def enforce(self, run: Run, baseline: Run | None = None) -> GateReport:
        """Raise ``GateFailed`` when the gate does not pass; return the report otherwise."""
        report = self.gate_report(run, baseline)
        if not report.passed:
            raise GateFailed(report)
        return report

    def __repr__(self) -> str:
        return f"Suite(name={self.name!r}, dataset={self.dataset.name!r}, checks={self.check_keys})"


__all__ = ["Suite"]
