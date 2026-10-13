"""Checks: the registry, the ``@check`` decorator and the built-in factories.

Built-in checks and user-defined checks have the same shape — see ``_base``.
"""

from evalstone.checks._base import CheckFn, FunctionCheck, Registry, check, registry
from evalstone.checks.deterministic import (
    contains,
    exact,
    json_schema,
    length,
    numeric_tolerance,
    python,
    regex,
)
from evalstone.checks.judge import judge

__all__ = [
    "CheckFn",
    "FunctionCheck",
    "Registry",
    "check",
    "contains",
    "exact",
    "json_schema",
    "judge",
    "length",
    "numeric_tolerance",
    "python",
    "regex",
    "registry",
]
