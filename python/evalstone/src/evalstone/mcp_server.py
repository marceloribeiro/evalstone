"""The Evalstone MCP server — run evals from inside a coding agent.

``evalstone mcp`` serves the project's ``evalstone.yaml`` over stdio using the
MCP Python SDK (2.x, ``MCPServer``). Tools return plain JSON-able dicts; errors
are returned as ``{"error": ...}`` results rather than protocol failures so an
agent can read them.

    claude mcp add evalstone -- evalstone mcp            # from the project directory
"""

from __future__ import annotations

import contextlib
import functools
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from evalstone import __version__
from evalstone._json import canonical
from evalstone.config import CONFIG_FILENAME, Config
from evalstone.dataset import Sample
from evalstone.output import Output
from evalstone.providers import Providers
from evalstone.run import Run, compare
from evalstone.score import Context, MemoryCache

INSTRUCTIONS = """Evalstone evaluates an LLM feature against a golden dataset with checks and a
gate. Typical loop: list_suites → run_suite → read the failures → change the prompt/code →
run_suite again → compare_runs. judge_output grades one answer with a named judge check.
record_sample appends a case to a dataset so the golden set grows while you work."""


class MissingExtra(RuntimeError):
    """The ``mcp`` extra is not installed."""


def _config_file(config_path: str | Path | None) -> Path:
    """The file ``Config.load`` would read for ``config_path`` (dir → its evalstone.yaml)."""
    p = Path(config_path or CONFIG_FILENAME)
    if p.is_dir():
        p = p / CONFIG_FILENAME
    return p.resolve()


def _under(root: Path, p: str | Path) -> Path:
    """``p`` resolved against the project root unless it is absolute."""
    q = Path(p).expanduser()
    return q if q.is_absolute() else root / q


class Session:
    """State that outlives one tool call.

    The config is re-read on every call (edits to the YAML, datasets and check
    modules are picked up without a restart), but the provider registry — one
    HTTP client per provider — and the judge cache are kept while the config's
    provider section is unchanged, so a long session neither leaks a connection
    pool per call nor re-pays a verdict it already has. Tool bodies run under
    ``lock``: the SDK dispatches sync tools on worker threads, and the registry,
    ``sys.modules`` eviction and the JSONL files are not safe to share.
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = config_path
        self.lock = threading.Lock()
        self.cache = MemoryCache()
        self._providers: Providers | None = None
        self._providers_key: str | None = None

    def config(self) -> Config:
        cfg = Config.load(self.config_path or CONFIG_FILENAME)
        if cfg.attached:
            return cfg  # judges go through the center's proxy; targets use cfg's local registry
        key = canonical(
            {
                "providers": {k: v.model_dump(mode="json") for k, v in cfg.providers.items()},
                "default_model": cfg.judges.default_model,
                "prices": cfg.prices,
            }
        )
        if self._providers is None or key != self._providers_key:
            self.close()
            self._providers = Providers(
                cfg.providers, default_model=cfg.judges.default_model, prices=cfg.prices
            )
            self._providers_key = key
        cfg._providers = self._providers
        return cfg

    def context(self, cfg: Config) -> Context:
        if cfg.attached:
            return cfg.context()  # center proxy, center cache, per-check overrides, labels
        return Context(providers=cfg.provider_registry(), cache=self.cache)

    def root(self) -> Path:
        """Where relative report paths live: the config's directory, else the cwd."""
        try:
            return self.config().root
        except FileNotFoundError:
            return Path.cwd()

    def close(self) -> None:
        if self._providers is not None:
            self._providers.close()
            self._providers = None
            self._providers_key = None

    def guard(self, fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        """Serialise the call, keep stray stdout off the wire, return errors as results.

        Anything a check or target prints goes to stderr: the SDK diverts fd 1
        while serving, but Python's own stdout buffer would still flush onto the
        wire once the transport restores it.
        """

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            with self.lock, contextlib.redirect_stdout(sys.stderr):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    return {"error": f"{type(exc).__name__}: {exc}"}

        return wrapper


Failures = Annotated[int, Field(ge=0, description="How many failing results to include")]


def _run_payload(run: Run, *, failures: int) -> dict[str, Any]:
    s = run.summary
    failing = run.failures()
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
            for r in failing[:failures]
        ],
        "failures_total": len(failing),
    }


def build_server(config_path: str | Path | None = None) -> Any:
    """An ``MCPServer`` whose tools operate on one ``evalstone.yaml``.

    The config is loaded per call so edits to the YAML, the dataset or the
    project's check modules are picked up without restarting the server; see
    ``Session`` for what is kept between calls. Relative paths in tool arguments
    are resolved against the config's directory.
    """
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise MissingExtra("the MCP server needs the SDK: pip install 'evalstone[mcp]'") from exc

    server = MCPServer(
        "evalstone",
        description="Run LLM evals (suites, judges, datasets) for this project.",
        instructions=INSTRUCTIONS,
        version=__version__,
    )
    session = Session(config_path)

    def tool(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        return server.tool()(session.guard(fn))

    @tool
    def list_suites() -> dict[str, Any]:
        """Suites, datasets and checks defined in evalstone.yaml."""
        cfg = session.config()
        cfg.activate()
        from evalstone.checks import registry

        return {
            "project": cfg.project,
            "config": str(_config_file(config_path)),
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

    @tool
    def run_suite(
        suite: str,
        report: str | None = None,
        baseline: str | None = None,
        failures: Failures = 20,
    ) -> dict[str, Any]:
        """Run a suite against its target. Returns the summary, per-check rates, the
        gate verdict and the failing results (with reasons). Writes the JSON report
        (default: the config's `report` path; relative paths are under the project
        root) so compare_runs/get_run can read it."""
        cfg = session.config()
        s, target = cfg.suite(suite)
        base = Run.from_json(_under(cfg.root, baseline)) if baseline else None
        try:
            run = s.run(target, baseline=base, trigger="mcp", ctx=session.context(cfg))
        finally:
            close = getattr(target, "close", None)
            if callable(close):
                close()
        out = _under(cfg.root, report or cfg.report)
        run.to_json(out)
        return {**_run_payload(run, failures=failures), "report": str(out)}

    @tool
    def judge_output(
        check: str, output: Any, input: Any = None, expected: Any = None
    ) -> dict[str, Any]:
        """Score one output with a check from evalstone.yaml (a judge, or any check
        type). `output` is the text, or a structured value such as `{"steps": [...]}`
        for trajectory checks; `input` and `expected` are the sample fields the
        check may need."""
        cfg = session.config()
        cfg.activate()
        chk = cfg.check(check)
        sample = Sample(input=input if input is not None else "", expected=expected)
        score = chk.evaluate(sample, Output(value=output), session.context(cfg))
        return {
            "check": check,
            "kind": str(chk.kind),
            "value": score.value,
            "passed": score.passed,
            "reason": score.reason,
            "error": score.error,
            "cost_usd": score.cost_usd,
        }

    @tool
    def record_sample(
        dataset: str,
        input: Any,
        expected: Any = None,
        tags: list[str] | None = None,
        id: str | None = None,
    ) -> dict[str, Any]:
        """Append a sample to a dataset's JSONL (source=harvested). The dataset's
        content hash changes, so later runs pin the new version."""
        cfg = session.config()
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
        row = canonical(sample.model_dump(mode="json", exclude_defaults=True)) + "\n"
        with path.open("a+b") as fh:
            fh.seek(0, 2)
            if fh.tell() > 0:  # a file whose last line lacks its newline
                fh.seek(-1, 2)
                if fh.read(1) != b"\n":
                    fh.write(b"\n")
            fh.write(row.encode("utf-8"))
        count = len(cfg.dataset(dataset))
        return {"dataset": dataset, "sample_id": sample.id, "path": str(path), "samples": count}

    @tool
    def compare_runs(a: str, b: str) -> dict[str, Any]:
        """Diff two JSON reports (paths, relative to the project root): regressions,
        improvements, metric deltas."""
        root = session.root()
        cmp = compare(Run.from_json(_under(root, a)), Run.from_json(_under(root, b)))
        return cmp.model_dump(mode="json")

    @tool
    def get_run(report: str, failures: Failures = 20) -> dict[str, Any]:
        """Read a saved JSON report (path relative to the project root): summary,
        per-check rates, gate, failures."""
        run = Run.from_json(_under(session.root(), report))
        return _run_payload(run, failures=failures)

    server.evalstone_session = session  # type: ignore[attr-defined]
    return server


def serve(config_path: str | Path | None = None) -> None:
    """Run the server over stdio (what ``evalstone mcp`` does)."""
    server = build_server(config_path)
    try:
        server.run("stdio")
    finally:
        server.evalstone_session.close()


__all__ = ["MissingExtra", "Session", "build_server", "serve"]
