"""Samples and datasets.

A ``Sample`` is one case: an input, an optional reference (``expected``), free
metadata and tags. A ``Dataset`` is a named list of samples whose
``content_hash`` identifies the exact version a run was executed against.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evalstone._json import canonical, sha256


class Source(StrEnum):
    MANUAL = "manual"
    HARVESTED = "harvested"
    SYNTHETIC = "synthetic"


class Sample(BaseModel):
    """One evaluation case.

    ``id`` defaults to a hash of ``(input, expected)``: two samples with the same
    input and reference are the same case even if tagged differently — give
    explicit ids when you need both. ``metadata`` is free-form annotation and is
    **not** part of the dataset version (``Dataset.content_hash``); anything a
    check reads to score belongs in ``input`` or ``expected``.
    """

    model_config = ConfigDict(frozen=True)

    id: str = ""
    input: Any
    expected: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    source: Source = Source.MANUAL

    @model_validator(mode="after")
    def _default_id(self) -> Sample:
        if not self.id:
            digest = sha256({"input": self.input, "expected": self.expected})[:16]
            object.__setattr__(self, "id", digest)
        return self

    def content(self) -> dict[str, Any]:
        """The fields that define this sample's identity for hashing."""
        return {
            "id": self.id,
            "input": self.input,
            "expected": self.expected,
            "tags": sorted(self.tags),
        }


class Dataset:
    """A named, ordered collection of samples with a reproducible content hash."""

    def __init__(self, name: str, samples: Iterable[Sample] = ()) -> None:
        self.name = name
        self._samples: list[Sample] = list(samples)
        counts = Counter(s.id for s in self._samples)
        dupes = sorted(i for i, n in counts.items() if n > 1)
        if dupes:
            derived = any(s.id in dupes and not _explicit_id(s) for s in self._samples)
            hint = (
                " (ids are derived from input+expected; give explicit `id`s to keep both)"
                if derived
                else ""
            )
            raise ValueError(f"dataset {name!r} has duplicate sample ids: {dupes}{hint}")

    # ── construction ─────────────────────────────────────────────────────

    @classmethod
    def from_jsonl(cls, path: str | Path, name: str | None = None) -> Dataset:
        """Load one JSON object per line. Blank lines are skipped."""
        path = Path(path)
        samples: list[Sample] = []
        with path.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                try:
                    samples.append(Sample.model_validate(json.loads(line)))
                except (json.JSONDecodeError, ValueError) as exc:
                    raise ValueError(f"{path}:{lineno}: invalid sample: {exc}") from exc
        return cls(name or path.stem, samples)

    @classmethod
    def from_records(cls, name: str, records: Iterable[dict[str, Any]]) -> Dataset:
        return cls(name, (Sample.model_validate(r) for r in records))

    def to_jsonl(self, path: str | Path) -> None:
        path = Path(path)
        with path.open("w", encoding="utf-8") as fh:
            for s in self._samples:
                fh.write(canonical(s.model_dump(mode="json", exclude_defaults=True)) + "\n")

    # ── identity ─────────────────────────────────────────────────────────

    @cached_property
    def content_hash(self) -> str:
        """sha256 over the ordered sample contents — the dataset *version*.

        Covers id, input, expected and tags; ``metadata`` and ``source`` are
        deliberately outside the version. Samples are frozen, so this is cached.
        """
        return sha256([s.content() for s in self._samples])

    # ── access ───────────────────────────────────────────────────────────

    @property
    def samples(self) -> list[Sample]:
        return list(self._samples)

    def __len__(self) -> int:
        return len(self._samples)

    def __iter__(self) -> Iterator[Sample]:
        return iter(self._samples)

    def __getitem__(self, sample_id: str) -> Sample:
        for s in self._samples:
            if s.id == sample_id:
                return s
        raise KeyError(sample_id)

    # ── slicing ──────────────────────────────────────────────────────────

    def filter(
        self,
        *,
        tags: Iterable[str] | None = None,
        predicate: Callable[[Sample], bool] | None = None,
        name: str | None = None,
    ) -> Dataset:
        """Samples carrying **all** ``tags`` and satisfying ``predicate``."""
        if isinstance(tags, str):
            tags = [tags]
        wanted = set(tags or ())
        kept = [
            s
            for s in self._samples
            if wanted.issubset(s.tags) and (predicate is None or predicate(s))
        ]
        return Dataset(name or f"{self.name}[filtered]", kept)

    def sample(self, n: int, *, seed: int = 0, name: str | None = None) -> Dataset:
        """A deterministic random subset of ``n`` samples (inner-loop subsets)."""
        rng = random.Random(seed)
        chosen = rng.sample(self._samples, k=min(n, len(self._samples)))
        return Dataset(name or f"{self.name}[sample:{n}]", chosen)

    def split(self, held_out: float = 0.2, *, seed: int = 0) -> tuple[Dataset, Dataset]:
        """Deterministic (iterate, held_out) split. The held-out slice is never iterated on."""
        if not 0 < held_out < 1:
            raise ValueError("held_out must be between 0 and 1")
        ids = sorted(s.id for s in self._samples)
        rng = random.Random(seed)
        rng.shuffle(ids)
        cut = round(len(ids) * held_out)
        held = set(ids[:cut])
        return (
            Dataset(f"{self.name}[iterate]", [s for s in self._samples if s.id not in held]),
            Dataset(f"{self.name}[held-out]", [s for s in self._samples if s.id in held]),
        )

    def __repr__(self) -> str:
        return f"Dataset(name={self.name!r}, samples={len(self)}, hash={self.content_hash[:12]})"


def _explicit_id(sample: Sample) -> bool:
    return sample.id != sha256({"input": sample.input, "expected": sample.expected})[:16]
