"""Agent trajectory checks — assertions over the path, not the final answer.

The trajectory is a list of steps, each ``{"tool": <name>, "args": {...}}``
(extra keys are fine), read from ``output.value[steps]`` (default key
``steps``) or ``output.metadata[steps]``. Deterministic and free.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from evalstone.checks._base import FunctionCheck
from evalstone.dataset import Sample
from evalstone.output import Output
from evalstone.score import CheckKind, Score


def steps_of(output: Output, key: str = "steps") -> list[dict[str, Any]] | None:
    """The trajectory of an output, ``[]`` when it is recorded but empty, ``None``
    when no trajectory was recorded at all (no ``key`` list on the value or metadata)."""
    for source in (output.value, output.metadata):
        if isinstance(source, dict) and isinstance(source.get(key), list):
            return [s for s in source[key] if isinstance(s, dict)]
    return None


_NO_TRAJECTORY = "no trajectory recorded (expected a list under output.value[{key!r}])"


def _steps_or_error(output: Output, key: str) -> list[dict[str, Any]] | Score:
    steps = steps_of(output, key)
    if steps is None:
        return Score.errored(_NO_TRAJECTORY.format(key=key))
    return steps


def _args(step: dict[str, Any]) -> dict[str, Any]:
    """A step's args as a dict; non-dict args (raw tool-call logs) are kept under ``value``."""
    args = step.get("args")
    if isinstance(args, dict):
        return args
    return {} if args is None else {"value": args}


def _tools(steps: list[dict[str, Any]]) -> list[str]:
    return [str(s.get("tool", "")) for s in steps]


def tool_called(
    name: str,
    key: str | None = None,
    *,
    min_times: int = 1,
    max_times: int | None = None,
    steps: str = "steps",
    args: Callable[[dict[str, Any]], bool] | None = None,
) -> FunctionCheck:
    """``name`` was called ``min_times``..``max_times`` times, optionally with matching args."""

    def fn(sample: Sample, output: Output) -> Score:
        trajectory = _steps_or_error(output, steps)
        if isinstance(trajectory, Score):
            return trajectory
        calls = [s for s in trajectory if s.get("tool") == name]
        if args is not None:
            calls = [s for s in calls if args(_args(s))]
        n = len(calls)
        if n < min_times:
            return Score.fail(f"{name} called {n}x, expected ≥ {min_times}")
        if max_times is not None and n > max_times:
            return Score.fail(f"{name} called {n}x, expected ≤ {max_times}")
        return Score.ok(f"{name} called {n}x")

    return FunctionCheck(key or f"called_{name}", fn, kind=CheckKind.TRAJECTORY)


def tool_order(
    before: str, after: str, key: str | None = None, *, steps: str = "steps"
) -> FunctionCheck:
    """Every call to ``after`` is preceded by at least one call to ``before``."""

    def fn(sample: Sample, output: Output) -> Score:
        trajectory = _steps_or_error(output, steps)
        if isinstance(trajectory, Score):
            return trajectory
        seen_before = False
        for i, tool in enumerate(_tools(trajectory)):
            if tool == before:
                seen_before = True
            elif tool == after and not seen_before:
                return Score.fail(f"{after} at step {i} before any {before}")
        return Score.ok()

    return FunctionCheck(key or f"{before}_before_{after}", fn, kind=CheckKind.TRAJECTORY)


def max_steps(n: int, key: str = "max_steps", *, steps: str = "steps") -> FunctionCheck:
    """The trajectory has at most ``n`` steps."""

    def fn(sample: Sample, output: Output) -> Score:
        trajectory = _steps_or_error(output, steps)
        if isinstance(trajectory, Score):
            return trajectory
        count = len(trajectory)
        return Score.from_bool(count <= n, "" if count <= n else f"{count} steps > max {n}")

    return FunctionCheck(key, fn, kind=CheckKind.TRAJECTORY)


def no_repeated_calls(
    key: str = "no_repeated_calls", *, max_repeats: int = 1, steps: str = "steps"
) -> FunctionCheck:
    """No identical (tool, args) call happens more than ``max_repeats`` times — loop detection."""

    def fn(sample: Sample, output: Output) -> Score:
        trajectory = _steps_or_error(output, steps)
        if isinstance(trajectory, Score):
            return trajectory
        seen: dict[str, int] = {}
        for s in trajectory:
            sig = f"{s.get('tool')}:{sorted(_args(s).items())!r}"
            seen[sig] = seen.get(sig, 0) + 1
        loops = {sig: c for sig, c in seen.items() if c > max_repeats}
        if loops:
            worst = max(loops.items(), key=lambda kv: kv[1])
            return Score.fail(f"repeated call x{worst[1]}: {worst[0][:80]}")
        return Score.ok()

    return FunctionCheck(key, fn, kind=CheckKind.TRAJECTORY)


def finished(key: str = "finished", *, path: str = "answer") -> FunctionCheck:
    """The agent produced a final answer (``output.value[path]`` is non-empty)."""

    def fn(sample: Sample, output: Output) -> Score:
        value = output.value.get(path) if isinstance(output.value, dict) else None
        ok = value not in (None, "", [], {})
        return Score.from_bool(ok, "" if ok else f"no final {path}")

    return FunctionCheck(key, fn, kind=CheckKind.TRAJECTORY)


__all__ = ["finished", "max_steps", "no_repeated_calls", "steps_of", "tool_called", "tool_order"]
