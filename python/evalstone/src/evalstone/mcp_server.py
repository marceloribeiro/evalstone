"""The Evalstone MCP server — run evals from inside a coding agent.

``evalstone mcp`` serves the project's ``evalstone.yaml`` over stdio using the
MCP Python SDK (2.x, ``MCPServer``). Tools return plain JSON-able dicts; errors
are returned as ``{"error": ...}`` results rather than protocol failures so an
agent can read them.

    claude mcp add evalstone -- evalstone mcp            # from the project directory
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evalstone import __version__
from evalstone.config import CONFIG_FILENAME, Config
from evalstone.dataset import Sample
from evalstone.output import Output
from evalstone.run import Run, compare
from evalstone.score import Context

INSTRUCTIONS = """Evalstone evaluates an LLM feature against a golden dataset with checks and a
gate. Typical loop: list_suites → run_suite → read the failures → change the prompt/code →
run_suite again → compare_runs. judge_output grades one answer with a named judge check.
record_sample appends a case to a dataset so the golden set grows while you work."""


def _load(config_path: str | Path | None) -> Config:
    return Config.load(config_path or CONFIG_FILENAME)


def _run_payload(run: Run, *, failures: int) -> dict[str, Any]:
    s = run.summary
    return {
        "run_id": run.id,
        "suite": run.suite,
        "dataset": run.dataset,
        "dataset_hash": run.dataset_hash[:12],
        "git_sha": run.git_sha,
        "summary": {
            "samples": s.samples,
            "results": s.results,
            "pass_rate": round(s.pass_rate, 4),
            "mean_score": round(s.mean_score, 4),
            "errors": s.errors,
            "cost_usd": round(s.cost_usd, 6),
            "duration_ms": round(s.duration_ms, 1),
        },
        "per_check": [
            {
                "key": c.key,
                "pass_rate": round(c.pass_rate, 4),
                "mean_score": round(c.mean_score, 4),
                "errors": c.errors,
            }
            for c in s.per_check
        ],
        "gate": {"passed": run.gate_passed, "lines": run.gate_lines},
        "failures": [
            {
                "sample_id": r.sample_id,
                "check": r.check_key,
                "value": round(r.score.value, 4),
                "reason": r.score.reason,
                "error": r.score.error,
                "output": r.output.text[:500],
            }
            for r in run.failures()[:failures]
        ],
        "failures_total": len(run.failures()),
    }


def build_server(config_path: str | Path | None = None) -> Any:
    """An ``MCPServer`` whose tools operate on one ``evalstone.yaml``.

    The config is loaded lazily per call so edits to the YAML, the dataset or the
    project's check modules are picked up without restarting the server.
    """
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError("the MCP server needs the SDK: pip install 'evalstone[mcp]'") from exc

    server = MCPServer(
        "evalstone",
        description="Run LLM evals (suites, judges, datasets) for this project.",
        instructions=INSTRUCTIONS,
        version=__version__,
    )

    @server.tool()
    def list_suites() -> dict[str, Any]:
        """Suites, datasets and checks defined in evalstone.yaml."""
        try:
            cfg = _load(config_path)
            cfg.activate()
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
        from evalstone.checks import registry

        return {
            "project": cfg.project,
            "config": str(cfg.root / CONFIG_FILENAME),
            "datasets": {k: str(cfg.root / v) for k, v in cfg.datasets.items()},
            "checks": {k: v.get("type") for k, v in cfg.checks.items()},
            "registered_checks": registry.keys(),
            "suites": {
                name: {
                    "dataset": s.dataset,
                    "target": s.target.get("kind"),
                    "checks": s.checks,
                    "gate": s.gate.model_dump(exclude_none=True) if s.gate else None,
                }
                for name, s in cfg.suites.items()
            },
        }

    @server.tool()
    def run_suite(
        suite: str,
        report: str | None = None,
        baseline: str | None = None,
        failures: int = 20,
    ) -> dict[str, Any]:
        """Run a suite against its target. Returns the summary, per-check rates, the
        gate verdict and the failing results (with reasons). Writes the JSON report
        (default: the config's `report` path) so compare_runs/get_run can read it."""
        try:
            cfg = _load(config_path)
            s, target = cfg.suite(suite)
            base = Run.from_json(baseline) if baseline else None
            run = s.run(target, baseline=base, trigger="mcp", ctx=cfg.context())
            out = Path(report) if report else cfg.root / cfg.report
            run.to_json(out)
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
        return {**_run_payload(run, failures=failures), "report": str(out)}

    @server.tool()
    def judge_output(
        check: str, output: str, input: Any = None, expected: Any = None
    ) -> dict[str, Any]:
        """Score one output with a check from evalstone.yaml (a judge, or any check
        type). `input` and `expected` are the sample fields the check may need."""
        try:
            cfg = _load(config_path)
            cfg.activate()
            chk = cfg.check(check)
            sample = Sample(input=input if input is not None else "", expected=expected)
            ctx: Context = cfg.context()
            score = chk.evaluate(sample, Output(value=output), ctx)
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
        return {
            "check": check,
            "kind": str(chk.kind),
            "value": score.value,
            "passed": score.passed,
            "reason": score.reason,
            "error": score.error,
            "cost_usd": score.cost_usd,
        }

    @server.tool()
    def record_sample(
        dataset: str,
        input: Any,
        expected: Any = None,
        tags: list[str] | None = None,
        id: str | None = None,
    ) -> dict[str, Any]:
        """Append a sample to a dataset's JSONL (source=harvested). The dataset's
        content hash changes, so later runs pin the new version."""
        try:
            cfg = _load(config_path)
            if dataset not in cfg.datasets:
                return {"error": f"unknown dataset {dataset!r}; known: {sorted(cfg.datasets)}"}
            path = cfg.root / cfg.datasets[dataset]
            sample = Sample(
                id=id or "", input=input, expected=expected, tags=tags or [], source="harvested"
            )
            existing = cfg.dataset(dataset) if path.exists() else None
            if existing is not None and any(s.id == sample.id for s in existing):
                return {"error": f"sample {sample.id} already exists in {dataset}"}
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(sample.model_dump(mode="json", exclude_defaults=True)) + "\n")
            count = len(cfg.dataset(dataset))
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
        return {"dataset": dataset, "sample_id": sample.id, "path": str(path), "samples": count}

    @server.tool()
    def compare_runs(a: str, b: str) -> dict[str, Any]:
        """Diff two JSON reports (paths): regressions, improvements, metric deltas."""
        try:
            cmp = compare(Run.from_json(a), Run.from_json(b))
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
        return cmp.model_dump(mode="json")

    @server.tool()
    def get_run(report: str, failures: int = 20) -> dict[str, Any]:
        """Read a saved JSON report: summary, per-check rates, gate, failures."""
        try:
            run = Run.from_json(report)
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
        return _run_payload(run, failures=failures)

    return server


def serve(config_path: str | Path | None = None) -> None:
    """Run the server over stdio (what ``evalstone mcp`` does)."""
    build_server(config_path).run("stdio")


__all__ = ["build_server", "serve"]
