"""pytest integration — a suite as a test, the gate as the assertion.

Registered automatically (entry point ``pytest11``) when evalstone is installed.

.. code-block:: python

    from evalstone.pytest_plugin import suite

    @suite("nightly")                      # runs the suite, fails on the gate
    def test_nightly(run):                 # optional body sees the Run
        assert run.summary.cost_usd < 1.0

Fixtures: ``evalstone_config`` (the loaded ``evalstone.yaml``), ``evalstone_run``
(a callable ``(suite, baseline=None) -> Run``) and ``evalstone_gate`` (same, but
fails the test when the gate does not pass). ``--evalstone-config`` points at
the YAML (default ``evalstone.yaml`` in the rootdir); ``--evalstone-baseline``
names a JSON report to gate regressions against.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from evalstone.config import CONFIG_FILENAME, Config
from evalstone.run import Run

MARK = "evalstone"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("evalstone")
    group.addoption(
        "--evalstone-config",
        action="store",
        default=None,
        help=f"path to {CONFIG_FILENAME} (default: {CONFIG_FILENAME} in the rootdir)",
    )
    group.addoption(
        "--evalstone-baseline",
        action="store",
        default=None,
        help="a saved JSON report to gate regressions against",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", f"{MARK}(suite): a test that runs an Evalstone suite and enforces its gate"
    )


def _gate_message(run: Run) -> str:
    lines = [f"evalstone gate FAILED for suite {run.suite!r} (run {run.id})", *run.gate_lines]
    failures = run.failures()
    if failures:
        lines.append(f"{len(failures)} failing result(s), first {min(10, len(failures))}:")
        for r in failures[:10]:
            flag = "error" if r.score.error else "fail"
            lines.append(f"  {flag} {r.sample_id} · {r.check_key} · {r.score.reason}")
    return "\n".join(lines)


@pytest.fixture(scope="session")
def evalstone_config(request: pytest.FixtureRequest) -> Config:
    """The project's evalstone.yaml (``--evalstone-config`` or the rootdir default)."""
    opt = request.config.getoption("--evalstone-config")
    path = Path(opt) if opt else Path(request.config.rootpath) / CONFIG_FILENAME
    try:
        return Config.load(path)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))


@pytest.fixture
def evalstone_run(request: pytest.FixtureRequest, evalstone_config: Config) -> Callable[..., Run]:
    """``evalstone_run("nightly", baseline=None) -> Run``. Writes the config's report."""

    def _run(suite: str, *, baseline: str | Path | None = None) -> Run:
        s, target = evalstone_config.suite(suite)
        base_opt = baseline or request.config.getoption("--evalstone-baseline")
        base = Run.from_json(base_opt) if base_opt else None
        run = s.run(target, baseline=base, trigger="ci", ctx=evalstone_config.context())
        run.to_json(evalstone_config.root / evalstone_config.report)
        return run

    return _run


@pytest.fixture
def evalstone_gate(evalstone_run: Callable[..., Run]) -> Callable[..., Run]:
    """Like ``evalstone_run`` but fails the test when the gate does not pass."""

    def _gate(suite: str, *, baseline: str | Path | None = None) -> Run:
        run = evalstone_run(suite, baseline=baseline)
        if run.gate_passed is False:
            pytest.fail(_gate_message(run), pytrace=False)
        return run

    return _gate


def suite(name: str, *, gate: bool = True, baseline: str | Path | None = None) -> Callable:
    """Turn a test function into an Evalstone suite run.

    The decorated function may take a ``run`` argument (the ``Run``) and any other
    fixtures. With ``gate=True`` a failing gate fails the test before the body runs.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        params = inspect.signature(fn).parameters
        wants_run = "run" in params
        extra = [p for p in params if p != "run"]

        @pytest.mark.evalstone(name)
        @functools.wraps(fn)
        def wrapper(evalstone_run, evalstone_gate, **kwargs):  # type: ignore[no-untyped-def]
            runner = evalstone_gate if gate else evalstone_run
            run = runner(name, baseline=baseline)
            return fn(run=run, **kwargs) if wants_run else fn(**kwargs)

        # pytest resolves fixtures from the signature: our two, plus the user's own.
        wrapper.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
            [
                inspect.Parameter("evalstone_run", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                inspect.Parameter("evalstone_gate", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                *[params[p] for p in extra],
            ]
        )
        return wrapper

    return decorator


__all__ = ["evalstone_config", "evalstone_gate", "evalstone_run", "suite"]
