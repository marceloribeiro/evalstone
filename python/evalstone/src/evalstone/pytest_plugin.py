"""pytest integration — a suite as a test, the gate as the assertion.

Registered automatically (entry point ``pytest11``) when evalstone is installed.

.. code-block:: python

    from evalstone.pytest_plugin import suite

    @suite("nightly")                      # runs the suite, fails on the gate
    def test_nightly(run):                 # optional body sees the Run
        assert run.summary.cost_usd < 1.0

Fixtures: ``evalstone_config`` (the loaded ``evalstone.yaml``), ``evalstone_run``
(a callable ``(suite, *, baseline=None, report=None) -> Run``) and
``evalstone_gate`` (same, but fails the test when the gate does not pass).
``--evalstone-config`` points at the YAML (default ``evalstone.yaml`` in the
rootdir); ``--evalstone-baseline`` names a saved report — or a directory of
per-suite reports — to gate regressions against.

Each suite writes its own report next to the config: ``evalstone-report.json``
becomes ``evalstone-report.<suite>.json``, so two suites in one session never
overwrite each other. Relative paths are resolved against the config's
directory. A suite without a ``gate:`` cannot pass ``evalstone_gate``.

Only ``pytest`` is imported at module level: the plugin loads into every pytest
session on the interpreter, so evalstone itself is imported inside the fixtures.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from evalstone.config import Config
    from evalstone.run import Run

MARK = "evalstone"
_CONFIG_FILENAME = "evalstone.yaml"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("evalstone")
    group.addoption(
        "--evalstone-config",
        action="store",
        default=None,
        help=f"path to {_CONFIG_FILENAME} (default: {_CONFIG_FILENAME} in the rootdir)",
    )
    group.addoption(
        "--evalstone-baseline",
        action="store",
        default=None,
        help="a saved JSON report, or a directory of per-suite reports, to gate "
        "regressions against (relative to the config's directory)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", f"{MARK}(suite): a test that runs an Evalstone suite and enforces its gate"
    )


def _gate_message(run: Run) -> str:
    lines = [f"evalstone gate FAILED for suite {run.suite!r} (run {run.id})", *run.gate_lines]
    lines.extend(run.failure_lines(10))
    return "\n".join(lines)


def _under(root: Path, p: str | Path) -> Path:
    q = Path(p).expanduser()
    return q if q.is_absolute() else root / q


def _suite_report_name(cfg: Config, suite: str) -> str:
    default = Path(cfg.report)
    return f"{default.stem}.{suite}{default.suffix}"


def _report_path(cfg: Config, suite: str, report: str | Path | None) -> Path:
    if report is not None:
        return _under(cfg.root, report)
    return cfg.root / Path(cfg.report).with_name(_suite_report_name(cfg, suite))


def _baseline_path(cfg: Config, suite: str, baseline: str | Path | None) -> Path | None:
    """A file as given; a directory → the suite's own report file inside it."""
    if baseline is None:
        return None
    path = _under(cfg.root, baseline)
    return path / _suite_report_name(cfg, suite) if path.is_dir() else path


@pytest.fixture(scope="session")
def evalstone_config(request: pytest.FixtureRequest) -> Config:
    """The project's evalstone.yaml (``--evalstone-config`` or the rootdir default)."""
    from evalstone.config import Config

    opt = request.config.getoption("--evalstone-config")
    path = Path(opt) if opt else Path(request.config.rootpath) / _CONFIG_FILENAME
    try:
        return Config.load(path)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))


@pytest.fixture
def evalstone_run(request: pytest.FixtureRequest, evalstone_config: Config) -> Callable[..., Run]:
    """``evalstone_run("nightly", baseline=None, report=None) -> Run``.

    Writes the suite's report (``evalstone-report.<suite>.json`` beside the config
    unless ``report`` is given). ``baseline`` defaults to ``--evalstone-baseline``.
    """
    from evalstone.run import Run

    def _run(
        suite: str, *, baseline: str | Path | None = None, report: str | Path | None = None
    ) -> Run:
        cfg = evalstone_config
        s, target = cfg.suite(suite)
        base_opt = baseline or request.config.getoption("--evalstone-baseline")
        base_path = _baseline_path(cfg, suite, base_opt)
        base = Run.from_json(base_path) if base_path else None
        try:
            run = s.run(target, baseline=base, trigger="ci", ctx=cfg.context())
        finally:
            close = getattr(target, "close", None)
            if callable(close):
                close()
        run.to_json(_report_path(cfg, suite, report))
        return run

    return _run


@pytest.fixture
def evalstone_gate(evalstone_run: Callable[..., Run]) -> Callable[..., Run]:
    """Like ``evalstone_run`` but fails the test when the gate does not pass — or
    when the suite has no ``gate:`` at all, since then nothing could fail it."""

    def _gate(
        suite: str, *, baseline: str | Path | None = None, report: str | Path | None = None
    ) -> Run:
        run = evalstone_run(suite, baseline=baseline, report=report)
        if run.gate_passed is None:
            pytest.fail(
                f"suite {suite!r} has no gate: add `gate:` to it in {_CONFIG_FILENAME}, "
                "or use evalstone_run to run it without one",
                pytrace=False,
            )
        if run.gate_passed is False:
            pytest.fail(_gate_message(run), pytrace=False)
        return run

    return _gate


def suite(name: str, *, gate: bool = True, baseline: str | Path | None = None) -> Callable:
    """Turn a test function (or method) into an Evalstone suite run.

    The decorated function may take a ``run`` argument (the ``Run``) and any other
    fixtures. With ``gate=True`` a failing gate fails the test before the body runs.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        params = list(inspect.signature(fn).parameters.values())
        receiver = params[0] if params and params[0].name in ("self", "cls") else None
        fixtures = [p for p in params if p is not receiver and p.name != "run"]
        wants_run = any(p.name == "run" for p in params)

        @pytest.mark.evalstone(name)
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            evalstone_run = kwargs.pop("evalstone_run")
            evalstone_gate = kwargs.pop("evalstone_gate")
            runner = evalstone_gate if gate else evalstone_run
            run = runner(name, baseline=baseline)
            if wants_run:
                kwargs["run"] = run
            return fn(*args, **kwargs)

        # pytest reads fixture names from the signature: the receiver stays first
        # (so a method's `self` is still stripped), then the user's own fixtures,
        # then the two we need.
        ours = [
            inspect.Parameter(n, inspect.Parameter.KEYWORD_ONLY)
            for n in ("evalstone_run", "evalstone_gate")
        ]
        wrapper.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
            [*([receiver] if receiver else []), *fixtures, *ours]
        )
        return wrapper

    return decorator


__all__ = ["evalstone_config", "evalstone_gate", "evalstone_run", "suite"]
