"""Human labels — the check of last resort, and the ground truth judges are calibrated against.

A label is a person's verdict on one (sample, output) pair, stored as a JSONL
line and keyed by the sample id **and a hash of the output text**, so a label
never silently applies to a changed answer. ``evalstone label <report>`` writes
them; the ``human`` check reads them: a labelled output gets the label's
score, an unlabelled one is an error (never a pass).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from evalstone._json import sha256
from evalstone.checks._base import FunctionCheck
from evalstone.dataset import Sample
from evalstone.output import Output
from evalstone.score import CheckKind, Score


def output_hash(output: Output | str) -> str:
    text = output if isinstance(output, str) else output.text
    return sha256(text)[:16]


class Label(BaseModel):
    """One human verdict."""

    sample_id: str
    output_hash: str
    value: float = Field(ge=0.0, le=1.0)
    passed: bool
    notes: str = ""
    check: str | None = None  # which rubric/check the grade is for; None = overall
    labeler: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw: Any = None  # the original grade (e.g. 4 on a 1-5 scale)

    @property
    def key(self) -> tuple[str, str, str | None]:
        return (self.sample_id, self.output_hash, self.check)


class LabelStore:
    """Labels in a JSONL file. Later lines win for the same (sample, output, check)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._labels: dict[tuple[str, str, str | None], Label] = {}
        if self.path.exists():
            with self.path.open(encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, start=1):
                    if not line.strip():
                        continue
                    try:
                        label = Label.model_validate_json(line)
                    except ValueError as exc:
                        raise ValueError(f"{self.path}:{lineno}: invalid label: {exc}") from exc
                    self._labels[label.key] = label

    def __len__(self) -> int:
        return len(self._labels)

    def __iter__(self) -> Iterable[Label]:
        return iter(self._labels.values())

    def get(self, sample_id: str, output: Output | str, check: str | None = None) -> Label | None:
        return self._labels.get((sample_id, output_hash(output), check))

    def add(self, label: Label) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(label.model_dump_json() + "\n")
        self._labels[label.key] = label


def human(
    *, key: str = "human", labels: str | Path = "labels.jsonl", check: str | None = None
) -> FunctionCheck:
    """Score from a person's label for this (sample, output); unlabelled → error.

    ``check`` selects labels recorded for a specific rubric (``evalstone label
    --check``); ``None`` uses the overall grade.
    """
    store_path = Path(labels)
    cached: dict[str, Any] = {}

    def store() -> LabelStore:
        # One parse per file version: a stat per call (so labels added while a
        # long-lived server runs are seen), a re-read only when the file changed.
        try:
            st = store_path.stat()
            stamp: tuple[int, int] | None = (st.st_mtime_ns, st.st_size)
        except FileNotFoundError:
            stamp = None
        if cached.get("stamp", ...) != stamp:
            cached["store"] = LabelStore(store_path)
            cached["stamp"] = stamp
        return cached["store"]

    def fn(sample: Sample, output: Output) -> Score:
        label = store().get(sample.id, output, check)
        if label is None:
            return Score.errored(
                f"no human label for {sample.id} @ {output_hash(output)} "
                f"(run `evalstone label <report> --out {store_path}`)"
            )
        reason = label.notes or ("labelled pass" if label.passed else "labelled fail")
        return Score(
            value=label.value,
            passed=label.passed,
            reason=reason,
            raw={"labeler": label.labeler, "grade": label.raw, "at": label.created_at.isoformat()},
        )

    return FunctionCheck(key, fn, kind=CheckKind.HUMAN)


__all__ = ["Label", "LabelStore", "human", "output_hash"]
