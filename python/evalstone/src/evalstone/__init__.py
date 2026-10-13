"""Evalstone — the plug-and-play evals layer for LLM-based projects.

The library computes; it owns no database. See https://evalstone.com/docs.
"""

from evalstone import checks
from evalstone.checks import check, registry
from evalstone.dataset import Dataset, Sample, Source
from evalstone.gate import Gate, GateFailed, GateReport
from evalstone.output import Output
from evalstone.run import Comparison, Result, Run, RunSummary, compare, write_report
from evalstone.score import Check, CheckKind, Context, Score
from evalstone.suite import Suite
from evalstone.target import CallableTarget, HttpTarget, RecordedTarget, Target, target

__version__ = "0.1.0.dev1"

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
    "Output",
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
