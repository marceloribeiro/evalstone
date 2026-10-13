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
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from evalstone.center import CenterCache, CenterClient, CenterConfig, CenterProviders
from evalstone.checks import comparison, deterministic, rag, registry, safety, trajectory
from evalstone.checks.human import human as human_factory
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
    short_circuit: bool = False  # skip judge checks on a sample a cheap check already failed

    @field_validator("target")
    @classmethod
    def _needs_kind(cls, v: dict[str, Any]) -> dict[str, Any]:
        if "kind" not in v:
            raise ValueError("target needs a `kind` (callable | http | recorded | prompt)")
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
    center: CenterConfig | None = None  # attached: keys, judge model and cache live there
    # model → (USD per 1M input tokens, USD per 1M output tokens); overrides the built-in table
    prices: dict[str, tuple[float, float]] = Field(default_factory=dict)
    report: str = "evalstone-report.json"
    root: Path = Field(default=Path("."), exclude=True)
    _providers: Providers | CenterProviders | None = None
    _center_client: CenterClient | None = None
    _judge_settings: dict[str, Any] | None = None

    @property
    def attached(self) -> bool:
        return self.center is not None

    def center_client(self) -> CenterClient:
        if self.center is None:
            raise ValueError("this project is not attached to a center (no `center:` block)")
        if self._center_client is None:
            self._center_client = CenterClient(self.center)
        return self._center_client

    def judge_settings(self) -> dict[str, Any]:
        """The center's judge settings for this project, fetched once per config."""
        if self._judge_settings is None:
            self._judge_settings = self.center_client().judge_settings()
        return self._judge_settings

    def provider_registry(self) -> Providers | CenterProviders:
        """One registry per config: the center's proxy when attached, else local adapters."""
        if self._providers is None:
            if self.center is not None:
                self._providers = CenterProviders(
                    self.center_client(), default_model=self.judge_settings().get("default_model")
                )
            else:
                self._providers = Providers(
                    self.providers, default_model=self.judges.default_model, prices=self.prices
                )
        return self._providers

    def context(self, *, judge_model: str | None = None) -> Context:
        """The run context: model access for judges and prompt targets, plus a judge cache.

        ``judge_model`` overrides every judge's model for this context only (the
        CLI's ``--judge-model``) — judges and pairwise comparisons, never the target
        under test: the same suite, a different judge, one flag. Attached, the cache is
        the center's and the project's per-check judge models ride in ``extra``.
        """
        if self.center is None:
            return Context(providers=self.provider_registry(), judge_model=judge_model)
        client = self.center_client()
        settings = self.judge_settings()
        return Context(
            providers=self.provider_registry(),
            judge_model=judge_model,
            cache=CenterCache(client) if self.center.cache else Context().cache,
            extra={"center_client": client, "judge_models": dict(settings.get("overrides") or {})},
        )

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
            if kind == "human":  # the labels file lives relative to evalstone.yaml
                if self.center is not None and "labels" not in spec:
                    spec["labels"] = "center"  # attached: labels live in the center
                else:
                    spec["labels"] = self.root / spec.get("labels", "labels.jsonl")
            baseline = spec.get("baseline")
            if kind == "comparison.pairwise" and isinstance(baseline, dict) and "kind" in baseline:
                spec["baseline"] = self.target(baseline)  # a target spec → a Target
                # (a plain {sample_id: output} mapping is passed through as recorded outputs)
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
            if not spec.get("model"):
                raise ValueError(
                    "prompt target needs its own `model` — it is the system under test and must "
                    "not silently share judges.default_model (a model grading itself)"
                )
            spec["providers"] = self.provider_registry()
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
            short_circuit=sc.short_circuit,
        )
        return suite, self.target(sc.target)


# Check types `evalstone.yaml` may name: the deterministic factories by name, minus
# `python` (it takes a function, not YAML). Later modules extend this mapping.
FACTORIES: dict[str, Callable[..., Any]] = {
    name: getattr(deterministic, name) for name in deterministic.__all__ if name != "python"
}
FACTORIES["judge"] = judge_factory  # judge(key, rubric, *, scale, model, …)
FACTORIES["human"] = human_factory  # human(*, key, labels, check)
# Dotted types for the other families: rag.faithfulness, safety.refusal,
# trajectory.tool_called, comparison.pairwise, … — every factory accepts `key=`.
for _mod in (rag, safety, trajectory, comparison):
    for _name in _mod.__all__:
        _fn = getattr(_mod, _name)
        helper = _name.startswith(("is_", "parse_", "steps_"))
        if callable(_fn) and not isinstance(_fn, type) and not helper:
            FACTORIES[f"{_mod.__name__.rsplit('.', 1)[-1]}.{_name}"] = _fn


_LOADED: dict[tuple[str, str], tuple[int, dict[str, tuple[int, int]]]] = {}


def _project_modules(top: str, root_s: str) -> dict[str, tuple[int, int]]:
    """``{module: (mtime_ns, size)}`` for every cached module under ``top`` whose file
    lives under ``root``."""
    found: dict[str, tuple[int, int]] = {}
    for name, mod in list(sys.modules.items()):
        if name != top and not name.startswith(top + "."):
            continue
        file = getattr(mod, "__file__", None)
        if not file or not str(Path(file).resolve()).startswith(root_s + os.sep):
            continue
        try:
            st = os.stat(file)
        except OSError:
            continue
        found[name] = (st.st_mtime_ns, st.st_size)
    return found


def _load_module(dotted: str, root: Path) -> Any:
    """Import ``dotted`` from the project at ``root``.

    ``root`` is put on ``sys.path``. The module is reused when it was already
    imported from this root — by an earlier call, with none of the project's
    files under its top-level package changed since and the check registry not
    cleared in between, or by the caller itself — so a test that patches the
    project's modules and then runs a suite sees its patches, and a long-lived
    server still picks up edits.
    Otherwise everything cached under the top-level package — the chain, its
    siblings, its parents — is evicted first, whether it came from this root
    (so ``@check`` registrations re-run against a cleared registry) or from
    another project that happens to use the same module names, and a fresh
    import gives the module new globals, which is how the registry tells a
    re-import apart from a genuine duplicate key.
    """
    from evalstone.checks import registry

    root_s = str(root.resolve())
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    top = dotted.split(".")[0]
    key = (dotted, root_s)
    module = sys.modules.get(dotted)
    if module is not None:
        cached = _LOADED.get(key)
        if cached is not None:
            generation, snapshot = cached
            reuse = generation == registry.generation and _project_modules(top, root_s) == snapshot
        else:
            # imported by the caller itself (a test that patched it, say): keep it as
            # long as it is this project's file, not a namesake from another root
            file = getattr(module, "__file__", None)
            reuse = bool(file) and str(Path(file).resolve()).startswith(root_s + os.sep)
        if reuse:
            _LOADED[key] = (registry.generation, _project_modules(top, root_s))
            return module
    for name in [n for n in sys.modules if n == top or n.startswith(top + ".")]:
        del sys.modules[name]
    module = importlib.import_module(dotted)
    _LOADED[key] = (registry.generation, _project_modules(top, root_s))
    return module


def _import_callable(ref: str, root: Path) -> Any:
    """``"package.module:attr"`` → the attribute, imported from the project root."""
    if ":" not in ref:
        raise ValueError(f"callable target must be 'module:function', got {ref!r}")
    mod, _, attr = ref.partition(":")
    return getattr(_load_module(mod, root), attr)


__all__ = ["CONFIG_FILENAME", "Config", "JudgesConfig", "SuiteConfig"]
