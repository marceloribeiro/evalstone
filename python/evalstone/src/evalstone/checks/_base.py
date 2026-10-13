"""The check registry, ``FunctionCheck`` and the ``@check`` decorator.

Built-in checks and user-defined checks have the same shape. A decorated
function may return a ``Score``, a ``bool`` or a ``float`` in 0..1; the
decorator normalises it. Any exception raised inside a check becomes
``Score.errored(...)`` — a crashing check never passes and never takes the
run down.
"""

from __future__ import annotations

import functools
import inspect
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from evalstone.score import Check, CheckKind, Context, Score

if TYPE_CHECKING:
    from evalstone.dataset import Sample
    from evalstone.output import Output

CheckFn = Callable[..., "Score | bool | float"]


class Registry:
    """Checks by key. Registering the same key twice is an error unless ``replace=True``."""

    def __init__(self) -> None:
        self._checks: dict[str, Check] = {}

    def register(self, chk: Check, *, replace: bool = False) -> Check:
        if chk.key in self._checks and not replace:
            raise ValueError(f"check {chk.key!r} is already registered")
        self._checks[chk.key] = chk
        return chk

    def get(self, key: str) -> Check:
        try:
            return self._checks[key]
        except KeyError:
            raise KeyError(f"unknown check {key!r}; registered: {sorted(self._checks)}") from None

    def __contains__(self, key: str) -> bool:
        return key in self._checks

    def keys(self) -> list[str]:
        return sorted(self._checks)

    def clear(self) -> None:
        self._checks.clear()


registry = Registry()


def _normalise(result: Any) -> Score:
    if isinstance(result, Score):
        return result
    if isinstance(result, bool):
        return Score.from_bool(result)
    if isinstance(result, int | float):
        return Score.from_value(float(result))
    raise TypeError(f"check must return Score, bool or float, got {type(result).__name__}")


class FunctionCheck:
    """A plain function promoted to a ``Check``."""

    def __init__(
        self,
        key: str,
        fn: CheckFn,
        *,
        kind: CheckKind = CheckKind.DETERMINISTIC,
        version: int = 1,
        description: str = "",
    ) -> None:
        self.key = key
        self.kind = kind
        self.version = version
        self.description = description or (inspect.getdoc(fn) or "")
        self._fn = fn
        self._wants_ctx = "ctx" in inspect.signature(fn).parameters
        functools.update_wrapper(self, fn)

    def evaluate(self, sample: Sample, output: Output, ctx: Context) -> Score:
        started = time.perf_counter()
        try:
            if self._wants_ctx:
                result = self._fn(sample, output, ctx=ctx)
            else:
                result = self._fn(sample, output)
            score = _normalise(result)
        except Exception as exc:  # a crashing check is an errored score, never a pass
            score = Score.errored(f"{type(exc).__name__}: {exc}")
        elapsed = (time.perf_counter() - started) * 1000
        if score.latency_ms == 0.0:
            score = score.model_copy(update={"latency_ms": elapsed})
        return score

    def __call__(self, sample: Sample, output: Output, ctx: Context | None = None) -> Score:
        return self.evaluate(sample, output, ctx or Context())

    def __repr__(self) -> str:
        return f"<check {self.key} kind={self.kind} v{self.version}>"


def check(
    key: str,
    *,
    kind: CheckKind | str = CheckKind.DETERMINISTIC,
    version: int = 1,
    register: bool = True,
) -> Callable[[CheckFn], FunctionCheck]:
    """Turn ``fn(sample, output[, ctx]) -> Score | bool | float`` into a registered check.

    >>> @check("no_apology")
    ... def no_apology(sample, output):
    ...     return "sorry" not in output.text.lower()
    """

    def decorator(fn: CheckFn) -> FunctionCheck:
        chk = FunctionCheck(key, fn, kind=CheckKind(kind), version=version)
        if register:
            # Re-importing or reloading the module that defined a check redefines the
            # same function; that replaces. A *different* function under the same key
            # is still a duplicate error.
            previous = registry._checks.get(key)
            same_fn = previous is not None and (
                getattr(previous, "__module__", None),
                getattr(previous, "__qualname__", None),
            ) == (fn.__module__, fn.__qualname__)
            registry.register(chk, replace=same_fn)
        return chk

    return decorator


__all__ = ["CheckFn", "FunctionCheck", "Registry", "check", "registry"]
