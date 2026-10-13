"""Runs, results, summaries, the JSON report and run comparison."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from evalstone.output import Output
from evalstone.score import Score

DEFAULT_FAILURES = 10  # failing results listed by the CLI, the markdown report and the action


def display_reason(score: Score) -> str:
    """What to show for a result: its reason, else its error text, else nothing."""
    return score.reason or score.error or ""


def _cell(text: str) -> str:
    """One markdown table cell: no pipes or line breaks may leak out of it."""
    return text.replace("|", "\\|").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


class Result(BaseModel):
    """One sample x one check."""

    sample_id: str
    check_key: str
    tags: list[str] = Field(default_factory=list)
    output: Output
    score: Score


class CheckSummary(BaseModel):
    key: str
    n: int
    passed: int
    errors: int
    pass_rate: float
    mean_score: float
    cost_usd: float


class RunSummary(BaseModel):
    samples: int
    checks: int
    results: int
    passed: int
    errors: int
    pass_rate: float
    mean_score: float
    error_rate: float
    cost_usd: float
    duration_ms: float
    per_check: list[CheckSummary] = Field(default_factory=list)
    per_tag: dict[str, float] = Field(default_factory=dict)  # tag -> pass rate


def summarise(
    results: list[Result], *, samples: int, checks: int, duration_ms: float
) -> RunSummary:
    n = len(results)
    passed = sum(r.score.passed for r in results)
    errors = sum(r.score.error is not None for r in results)
    cost = sum(r.score.cost_usd for r in results) + sum(
        o.cost_usd for o in {r.sample_id: r.output for r in results}.values()
    )
    by_check: dict[str, list[Result]] = defaultdict(list)
    by_tag: dict[str, list[Result]] = defaultdict(list)
    for r in results:
        by_check[r.check_key].append(r)
        for t in r.tags:
            by_tag[t].append(r)
    per_check = [
        CheckSummary(
            key=k,
            n=len(rs),
            passed=sum(r.score.passed for r in rs),
            errors=sum(r.score.error is not None for r in rs),
            pass_rate=sum(r.score.passed for r in rs) / len(rs),
            mean_score=sum(r.score.value for r in rs) / len(rs),
            cost_usd=sum(r.score.cost_usd for r in rs),
        )
        for k, rs in sorted(by_check.items())
    ]
    return RunSummary(
        samples=samples,
        checks=checks,
        results=n,
        passed=passed,
        errors=errors,
        pass_rate=passed / n if n else 0.0,
        mean_score=sum(r.score.value for r in results) / n if n else 0.0,
        error_rate=errors / n if n else 0.0,
        cost_usd=cost,
        duration_ms=duration_ms,
        per_check=per_check,
        per_tag={t: sum(r.score.passed for r in rs) / len(rs) for t, rs in sorted(by_tag.items())},
    )


class Run(BaseModel):
    """One suite executed against one target. Serialisable; comparable to another run."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    suite: str
    dataset: str
    dataset_hash: str
    target: dict[str, Any]
    check_keys: list[str]
    git_sha: str | None = None
    trigger: str = "cli"
    baseline_run_id: str | None = None
    started_at: datetime
    finished_at: datetime
    results: list[Result]
    summary: RunSummary
    gate_passed: bool | None = None
    gate_lines: list[str] = Field(default_factory=list)

    # ── persistence ──────────────────────────────────────────────────────

    def to_json(self, path: str | Path | None = None, *, indent: int = 2) -> str:
        text = self.model_dump_json(indent=indent)
        if path is not None:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text + "\n", encoding="utf-8")
        return text

    @classmethod
    def from_json(cls, source: str | Path) -> Run:
        """Load from a file path, or from JSON text when ``source`` is a string that
        starts with ``{`` (the filesystem is never probed with document text)."""
        if isinstance(source, str) and source.lstrip().startswith("{"):
            return cls.model_validate_json(source)
        return cls.model_validate_json(Path(source).read_text(encoding="utf-8"))

    # ── views ────────────────────────────────────────────────────────────

    def failures(self) -> list[Result]:
        return [r for r in self.results if not r.score.passed]

    def failures_shown(
        self, limit: int = DEFAULT_FAILURES
    ) -> tuple[list[Result], list[Result], str]:
        """``(all failing, the first ``limit``, header suffix)``; ``limit <= 0`` shows none."""
        failing = self.failures()
        shown = failing[: max(limit, 0)]
        suffix = f", first {len(shown)}" if len(failing) > len(shown) else ""
        return failing, shown, suffix

    def failure_lines(self, limit: int = DEFAULT_FAILURES) -> list[str]:
        """Plain-text failing results: a header, then ``flag sample · check · reason``
        for the first ``limit``. Empty when nothing failed."""
        failing, shown, suffix = self.failures_shown(limit)
        if not failing:
            return []
        lines = [f"{len(failing)} failing result(s){suffix}:"]
        for r in shown:
            flag = "error" if r.score.error else "fail"
            lines.append(f"  {flag} {r.sample_id} · {r.check_key} · {display_reason(r.score)}")
        return lines

    def table(self) -> str:
        """A plain-text summary: per-check rows, then the totals line."""
        s = self.summary
        rows = [f"{'check':<28}{'n':>5}{'pass':>8}{'mean':>8}{'err':>5}{'cost':>10}"]
        for c in s.per_check:
            rows.append(
                f"{c.key:<28}{c.n:>5}{c.pass_rate:>8.1%}{c.mean_score:>8.3f}{c.errors:>5}"
                f"{c.cost_usd:>10.4f}"
            )
        rows.append("-" * 64)
        rows.append(
            f"{'total':<28}{s.results:>5}{s.pass_rate:>8.1%}{s.mean_score:>8.3f}{s.errors:>5}"
            f"{s.cost_usd:>10.4f}"
        )
        rows.append(
            f"run {self.id} · {self.suite} · {self.dataset}@{self.dataset_hash[:12]} · "
            f"{s.samples} samples · {s.duration_ms / 1000:.1f}s"
        )
        return "\n".join(rows)

    def markdown(self, *, failures: int = DEFAULT_FAILURES, title: str | None = None) -> str:
        """A GitHub-flavoured markdown report: verdict, per-check table, failures.

        ``failures`` caps the listed failing results; ``0`` lists none.
        """
        s = self.summary
        verdict = (
            "✅ gate passed"
            if self.gate_passed
            else "❌ gate failed"
            if self.gate_passed is False
            else "no gate"
        )
        head = title or f"Evalstone · `{self.suite}`"
        lines = [
            f"### {head} — {verdict}",
            "",
            f"`{self.dataset}@{self.dataset_hash[:12]}` · {s.samples} samples · "
            f"pass **{s.pass_rate:.1%}** · mean {s.mean_score:.3f} · errors {s.errors} · "
            f"cost ${s.cost_usd:.4f} · {s.duration_ms / 1000:.1f}s"
            + (f" · `{self.git_sha[:8]}`" if self.git_sha else ""),
            "",
            "| check | n | pass | mean | errors |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for c in s.per_check:
            lines.append(
                f"| `{_cell(c.key)}` | {c.n} | {c.pass_rate:.1%} | {c.mean_score:.3f} "
                f"| {c.errors} |"
            )
        if self.gate_lines:
            lines += ["", "<details><summary>gate</summary>", "", "```"]
            lines += self.gate_lines
            lines += ["```", "", "</details>"]
        failing, shown, suffix = self.failures_shown(failures)
        if shown:
            lines += [
                "",
                f"<details><summary>{len(failing)} failing result(s){suffix}</summary>",
                "",
                "| sample | check | value | reason |",
                "| --- | --- | ---: | --- |",
            ]
            for r in shown:
                flag = "⚠️ " if r.score.error else ""
                lines.append(
                    f"| `{_cell(r.sample_id)}` | `{_cell(r.check_key)}` | {r.score.value:.2f} | "
                    f"{flag}{_cell(display_reason(r.score))} |"
                )
            lines += ["", "</details>"]
        elif failing:
            lines += ["", f"{len(failing)} failing result(s)"]
        lines += ["", f"<sub>run `{self.id}` · evalstone</sub>"]
        return "\n".join(lines)

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)


class Flip(BaseModel):
    sample_id: str
    check_key: str
    before: Score
    after: Score


class Comparison(BaseModel):
    """Run B relative to run A, sample by sample."""

    a: str
    b: str
    same_dataset: bool
    pass_rate_delta: float
    mean_score_delta: float
    cost_delta: float
    regressions: list[Flip]
    improvements: list[Flip]
    only_in_a: list[str]
    only_in_b: list[str]

    def table(self) -> str:
        head = (
            f"{self.a} -> {self.b} · pass {self.pass_rate_delta:+.1%}"
            f" · mean {self.mean_score_delta:+.3f} · cost {self.cost_delta:+.4f}"
            + ("" if self.same_dataset else " · DIFFERENT DATASET")
        )
        counts = f"regressions: {len(self.regressions)}  improvements: {len(self.improvements)}"
        lines = [head, counts]
        for f in self.regressions:
            lines.append(
                f"  v {f.sample_id} {f.check_key}: {f.before.value:.2f} -> {f.after.value:.2f}"
                f" {f.after.reason}"
            )
        for f in self.improvements:
            lines.append(
                f"  ^ {f.sample_id} {f.check_key}: {f.before.value:.2f} -> {f.after.value:.2f}"
            )
        return "\n".join(lines)


def compare(a: Run, b: Run) -> Comparison:
    key = lambda r: (r.sample_id, r.check_key)  # noqa: E731
    ra = {key(r): r for r in a.results}
    rb = {key(r): r for r in b.results}
    regressions: list[Flip] = []
    improvements: list[Flip] = []
    for k in sorted(set(ra) & set(rb)):
        before, after = ra[k].score, rb[k].score
        if before.passed and not after.passed:
            regressions.append(Flip(sample_id=k[0], check_key=k[1], before=before, after=after))
        elif after.passed and not before.passed:
            improvements.append(Flip(sample_id=k[0], check_key=k[1], before=before, after=after))
    return Comparison(
        a=a.id,
        b=b.id,
        same_dataset=a.dataset_hash == b.dataset_hash,
        pass_rate_delta=b.summary.pass_rate - a.summary.pass_rate,
        mean_score_delta=b.summary.mean_score - a.summary.mean_score,
        cost_delta=b.summary.cost_usd - a.summary.cost_usd,
        regressions=regressions,
        improvements=improvements,
        only_in_a=sorted(f"{s}/{c}" for s, c in set(ra) - set(rb)),
        only_in_b=sorted(f"{s}/{c}" for s, c in set(rb) - set(ra)),
    )


def write_report(run: Run, path: str | Path = "evalstone-report.json") -> Path:
    p = Path(path)
    run.to_json(p)
    return p


__all__ = [
    "CheckSummary",
    "Comparison",
    "Flip",
    "Result",
    "Run",
    "RunSummary",
    "compare",
    "summarise",
    "write_report",
]
