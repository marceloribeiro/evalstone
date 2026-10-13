"""``evalstone.yaml`` — datasets, keyed checks, suites, gates, targets.

.. code-block:: yaml

    project: support-bot
    imports: [evals.checks]            # modules whose @check registrations to load
    datasets:
      golden: evals/golden.jsonl
    checks:                            # keyed check definitions: {type: <factory>, ...kwargs}
      must_include: { type: contains }
      short: { type: length, max_words: 120 }
    suites:
      nightly:
        dataset: golden
        target: { kind: callable, fn: "bot:answer" }   # or http / recorded
        checks: [must_include, short, no_apology]      # keys here or registered via imports
        gate: { min_pass_rate: 0.95 }
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from evalstone.checks import deterministic, registry
from evalstone.checks.judge import judge as judge_factory
from evalstone.dataset import Dataset
from evalstone.gate import Gate
from evalstone.providers import ProviderConfig, Providers
from evalstone.score import Check, Context
from evalstone.suite import Suite
from evalstone.target import Target
from evalstone.target import target as make_target

CONFIG_FILENAME = "evalstone.yaml"


class SuiteConfig(BaseModel):
    dataset: str
    target: dict[str, Any]
    checks: list[str]
    gate: Gate | None = None

    @field_validator("target")
    @classmethod
    def _needs_kind(cls, v: dict[str, Any]) -> dict[str, Any]:
        if "kind" not in v:
            raise ValueError("target needs a `kind` (callable | http | recorded)")
        return v


class JudgesConfig(BaseModel):
    default_model: str | None = None


class Config(BaseModel):
    project: str
    imports: list[str] = Field(default_factory=list)
    datasets: dict[str, str] = Field(default_factory=dict)
    checks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    suites: dict[str, SuiteConfig] = Field(default_factory=dict)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    judges: JudgesConfig = Field(default_factory=JudgesConfig)
    # model → (USD per 1M input tokens, USD per 1M output tokens); overrides the built-in table
    prices: dict[str, tuple[float, float]] = Field(default_factory=dict)
    report: str = "evalstone-report.json"
    root: Path = Field(default=Path("."), exclude=True)
    _providers: Providers | None = None

    def provider_registry(self) -> Providers:
        """One ``Providers`` per config (adapters are created lazily, keys read from env)."""
        if self._providers is None:
            self._providers = Providers(
                self.providers, default_model=self.judges.default_model, prices=self.prices
            )
        return self._providers

    def context(self) -> Context:
        """The run context: model access for judges and prompt targets, plus a judge cache."""
        return Context(providers=self.provider_registry())

    # ── loading ──────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        p = Path(path or CONFIG_FILENAME)
        if p.is_dir():
            p = p / CONFIG_FILENAME
        if not p.exists():
            raise FileNotFoundError(f"{p}: not found (run `evalstone init` to create one)")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        cfg = cls.model_validate(data)
        cfg.root = p.resolve().parent
        return cfg

    def activate(self) -> None:
        """Make the project importable and load ``imports`` so their checks register.

        A module already imported from *this* project is reloaded (so registrations
        re-run after the registry was cleared); one cached from another location —
        a different project with the same module name — is evicted first.
        """
        for mod in self.imports:
            _load_module(mod, self.root)

    # ── building objects ─────────────────────────────────────────────────

    def dataset(self, name: str) -> Dataset:
        try:
            rel = self.datasets[name]
        except KeyError:
            raise KeyError(f"unknown dataset {name!r}; known: {sorted(self.datasets)}") from None
        return Dataset.from_jsonl(self.root / rel, name=name)

    def check(self, key: str) -> Check:
        """A keyed check from the ``checks:`` section, else one registered via ``imports``."""
        if key in self.checks:
            spec = dict(self.checks[key])
            kind = spec.pop("type", None)
            if kind is None:
                raise ValueError(f"check {key!r} needs a `type`")
            factory = FACTORIES.get(kind)
            if factory is None:
                known = ", ".join(sorted(FACTORIES))
                raise ValueError(f"check {key!r}: unknown type {kind!r} (known: {known})")
            try:
                return factory(key=key, **spec)
            except TypeError as exc:
                raise ValueError(f"check {key!r} ({kind}): {exc}") from None
        return registry.get(key)

    def target(self, spec: dict[str, Any]) -> Target:
        spec = dict(spec)
        kind = spec.pop("kind")
        if kind == "callable":
            spec["fn"] = _import_callable(spec["fn"], self.root)
        if kind == "recorded" and "path" in spec:
            spec["path"] = self.root / spec["path"]
        if kind == "prompt":
            spec["providers"] = self.provider_registry()
            spec.setdefault("model", self.judges.default_model)
        return make_target(kind, **spec)

    def suite(self, name: str) -> tuple[Suite, Target]:
        try:
            sc = self.suites[name]
        except KeyError:
            raise KeyError(f"unknown suite {name!r}; known: {sorted(self.suites)}") from None
        self.activate()
        suite = Suite(
            name,
            dataset=self.dataset(sc.dataset),
            checks=[self.check(k) for k in sc.checks],
            gate=sc.gate,
        )
        return suite, self.target(sc.target)


# Check types `evalstone.yaml` may name: the deterministic factories by name, minus
# `python` (it takes a function, not YAML). Later modules extend this mapping.
FACTORIES: dict[str, Callable[..., Any]] = {
    name: getattr(deterministic, name) for name in deterministic.__all__ if name != "python"
}
FACTORIES["judge"] = judge_factory  # judge(key, rubric, *, scale, model, …)


def _load_module(dotted: str, root: Path) -> Any:
    """Import ``dotted`` from the project at ``root``, fresh.

    ``root`` is put on ``sys.path``. Everything cached under the module's top-level
    package — the chain, its siblings, its parents — is evicted first, whether it
    came from this root (so ``@check`` registrations re-run against a cleared
    registry) or from another project that happens to use the same module names.
    A fresh import gives the module new globals, which is how the registry tells
    a re-import apart from a genuine duplicate key.
    """
    root_s = str(root.resolve())
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    top = dotted.split(".")[0]
    for name in [n for n in sys.modules if n == top or n.startswith(top + ".")]:
        del sys.modules[name]
    return importlib.import_module(dotted)


def _import_callable(ref: str, root: Path) -> Any:
    """``"package.module:attr"`` → the attribute, imported from the project root."""
    if ":" not in ref:
        raise ValueError(f"callable target must be 'module:function', got {ref!r}")
    mod, _, attr = ref.partition(":")
    return getattr(_load_module(mod, root), attr)


__all__ = ["CONFIG_FILENAME", "Config", "JudgesConfig", "SuiteConfig"]
