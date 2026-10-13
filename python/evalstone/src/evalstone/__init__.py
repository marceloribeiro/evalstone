"""Evalstone — the plug-and-play evals layer for LLM-based projects.

The library computes; it owns no database. See https://evalstone.com/docs.
"""

from evalstone.checks import check, registry
from evalstone.dataset import Dataset, Sample, Source
from evalstone.output import Output
from evalstone.score import Check, CheckKind, Context, Score

__version__ = "0.1.0.dev1"

__all__ = [
    "Check",
    "CheckKind",
    "Context",
    "Dataset",
    "Output",
    "Sample",
    "Score",
    "Source",
    "__version__",
    "check",
    "registry",
]
