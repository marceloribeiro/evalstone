"""Evalstone — the plug-and-play evals layer for LLM-based projects.

The library computes; it owns no database. See https://evalstone.com/docs.
"""

import sys
import types
from importlib import import_module
from typing import TYPE_CHECKING, Any

__version__ = "0.2.0"

# Exports resolve on first access (PEP 562) so that importing the package — which
# the pytest plugin does in every pytest session on the interpreter — costs
# nothing until a name is used.
_EXPORTS: dict[str, str] = {
    "check": "evalstone.checks",
    "registry": "evalstone.checks",
    "Dataset": "evalstone.dataset",
    "Sample": "evalstone.dataset",
    "Source": "evalstone.dataset",
    "Gate": "evalstone.gate",
    "GateFailed": "evalstone.gate",
    "GateReport": "evalstone.gate",
    "Output": "evalstone.output",
    "Providers": "evalstone.providers",
    "Comparison": "evalstone.run",
    "Result": "evalstone.run",
    "Run": "evalstone.run",
    "RunSummary": "evalstone.run",
    "compare": "evalstone.run",
    "write_report": "evalstone.run",
    "Check": "evalstone.score",
    "CheckKind": "evalstone.score",
    "Context": "evalstone.score",
    "MemoryCache": "evalstone.score",
    "Score": "evalstone.score",
    "Suite": "evalstone.suite",
    "CallableTarget": "evalstone.target",
    "HttpTarget": "evalstone.target",
    "PromptTarget": "evalstone.target",
    "RecordedTarget": "evalstone.target",
    "Target": "evalstone.target",
    "target": "evalstone.target",
}

if TYPE_CHECKING:
    from evalstone import checks
    from evalstone.checks import check, registry
    from evalstone.dataset import Dataset, Sample, Source
    from evalstone.gate import Gate, GateFailed, GateReport
    from evalstone.output import Output
    from evalstone.providers import Providers
    from evalstone.run import Comparison, Result, Run, RunSummary, compare, write_report
    from evalstone.score import Check, CheckKind, Context, MemoryCache, Score
    from evalstone.suite import Suite
    from evalstone.target import (
        CallableTarget,
        HttpTarget,
        PromptTarget,
        RecordedTarget,
        Target,
        target,
    )


class _Package(types.ModuleType):
    """``evalstone.target`` is the factory function, as it always was, even though a
    submodule of the same name exists: importing that submodule makes the import
    system bind it onto the package, which the setter below ignores."""

    @property
    def target(self) -> Any:
        return import_module("evalstone.target").target

    @target.setter
    def target(self, value: Any) -> None:
        pass


sys.modules[__name__].__class__ = _Package


def __getattr__(name: str) -> Any:
    if name == "checks":
        return import_module("evalstone.checks")
    try:
        module = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module 'evalstone' has no attribute {name!r}") from None
    value = getattr(import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(__all__) | {n for n in globals() if n.startswith("__")})


__all__ = [
    "CallableTarget",
    "Check",
    "CheckKind",
    "Comparison",
    "Context",
    "Dataset",
    "Gate",
    "GateFailed",
    "GateReport",
    "HttpTarget",
    "MemoryCache",
    "Output",
    "PromptTarget",
    "Providers",
    "RecordedTarget",
    "Result",
    "Run",
    "RunSummary",
    "Sample",
    "Score",
    "Source",
    "Suite",
    "Target",
    "__version__",
    "check",
    "checks",
    "compare",
    "registry",
    "target",
    "write_report",
]
