"""Built-in deterministic checks.

Pure code, no model, free, repeatable. Each factory returns a ``FunctionCheck``
you can hand to a suite or register under a key of your choosing. Where a
check compares against a reference, the reference comes from
``sample.expected`` — the whole value, or a dotted ``path`` into it — unless a
literal ``expected``/``needles`` is given.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterable
from typing import Any

from evalstone.checks import CheckFn, FunctionCheck
from evalstone.dataset import Sample
from evalstone.output import Output
from evalstone.score import CheckKind, Score

_MISSING = object()


def _dig(value: Any, path: str | None) -> Any:
    """Follow a dotted path into dicts/lists; ``_MISSING`` when absent."""
    if path is None:
        return value
    cur = value
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return _MISSING
    return cur


def _reference(sample: Sample, path: str | None, literal: Any) -> Any:
    if literal is not _MISSING:
        return literal
    ref = _dig(sample.expected, path)
    if ref is _MISSING:
        where = f"expected.{path}" if path else "expected"
        raise ValueError(f"sample {sample.id} has no {where}")
    return ref


def _as_json(output: Output) -> Any:
    """The output as a JSON value: parse ``str`` values, pass everything else through."""
    if isinstance(output.value, str):
        return json.loads(output.value)
    return output.value


def _as_number(value: Any) -> float:
    if isinstance(value, bool):
        raise TypeError("boolean is not a number")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return float(value.strip())
    raise TypeError(f"not a number: {value!r}")


# ── factories ───────────────────────────────────────────────────────────────


def exact(
    key: str = "exact",
    *,
    expected: Any = _MISSING,
    path: str | None = None,
    case_sensitive: bool = True,
    strip: bool = True,
) -> FunctionCheck:
    """The output equals the reference. Strings are compared as text (optionally
    case-insensitive and stripped); anything else by JSON equality."""

    def fn(sample: Sample, output: Output) -> Score:
        ref = _reference(sample, path, expected)
        if isinstance(ref, str):
            got = output.text
            if strip:
                got, ref = got.strip(), ref.strip()
            if not case_sensitive:
                got, ref = got.lower(), ref.lower()
            ok = got == ref
        else:
            try:
                ok = _as_json(output) == ref
            except json.JSONDecodeError:
                return Score.fail(f"output is not valid JSON; expected {ref!r}")
        return Score.from_bool(ok, "" if ok else f"expected {ref!r}, got {output.text!r}")

    return FunctionCheck(key, fn, kind=CheckKind.DETERMINISTIC)


def contains(
    key: str = "contains",
    *,
    needles: Iterable[str] | str = _MISSING,  # type: ignore[assignment]
    path: str | None = "must_include",
    require_all: bool = True,
    case_sensitive: bool = False,
) -> FunctionCheck:
    """Every (or any) needle appears in the output text. Needles default to
    ``sample.expected.must_include`` (a string or a list)."""

    def fn(sample: Sample, output: Output) -> Score:
        ref = _reference(sample, path, needles)
        wanted = [ref] if isinstance(ref, str) else [str(n) for n in ref]
        hay = output.text if case_sensitive else output.text.lower()
        hits = [n for n in wanted if (n if case_sensitive else n.lower()) in hay]
        missing = [n for n in wanted if n not in hits]
        ok = not missing if require_all else bool(hits)
        value = len(hits) / len(wanted) if wanted else 1.0
        reason = "" if ok else f"missing {missing!r}"
        return Score(value=value, passed=ok, reason=reason)

    return FunctionCheck(key, fn, kind=CheckKind.DETERMINISTIC)


def regex(
    pattern: str,
    key: str = "regex",
    *,
    flags: int = 0,
    must_match: bool = True,
) -> FunctionCheck:
    """The output text matches (or, with ``must_match=False``, does not match) ``pattern``."""
    compiled = re.compile(pattern, flags)

    def fn(sample: Sample, output: Output) -> Score:
        found = compiled.search(output.text) is not None
        ok = found if must_match else not found
        verb = "did not match" if must_match else "matched"
        return Score.from_bool(ok, "" if ok else f"{verb} /{pattern}/")

    return FunctionCheck(key, fn, kind=CheckKind.DETERMINISTIC)


def json_schema(schema: dict[str, Any] | type, key: str = "json_schema") -> FunctionCheck:
    """The output is valid JSON and conforms to ``schema`` — a JSON Schema dict or a
    pydantic model class."""
    validate: Callable[[Any], None]
    if isinstance(schema, dict):
        import jsonschema

        validator = jsonschema.Draft202012Validator(schema)

        def validate(value: Any) -> None:
            errors = sorted(validator.iter_errors(value), key=lambda e: list(e.path))
            if errors:
                first = errors[0]
                where = "/".join(str(p) for p in first.path) or "<root>"
                raise ValueError(f"{where}: {first.message}")

    else:
        from pydantic import TypeAdapter, ValidationError

        adapter = TypeAdapter(schema)

        def validate(value: Any) -> None:
            try:
                adapter.validate_python(value)
            except ValidationError as exc:
                first = exc.errors()[0]
                where = "/".join(str(p) for p in first["loc"]) or "<root>"
                raise ValueError(f"{where}: {first['msg']}") from None

    def fn(sample: Sample, output: Output) -> Score:
        try:
            value = _as_json(output)
        except json.JSONDecodeError as exc:
            return Score.fail(f"not valid JSON: {exc.msg}")
        try:
            validate(value)
        except ValueError as exc:
            return Score.fail(f"schema: {exc}")
        return Score.ok()

    return FunctionCheck(key, fn, kind=CheckKind.DETERMINISTIC)


def numeric_tolerance(
    key: str = "numeric_tolerance",
    *,
    expected: Any = _MISSING,
    path: str | None = None,
    output_path: str | None = None,
    abs_tol: float = 0.0,
    rel_tol: float = 0.0,
) -> FunctionCheck:
    """The output number is within ``abs_tol`` / ``rel_tol`` of the reference number.
    ``output_path`` digs into a JSON output; otherwise the whole output is the number."""

    def fn(sample: Sample, output: Output) -> Score:
        ref = _as_number(_reference(sample, path, expected))
        raw = output.value if output_path is None else _dig(_as_json(output), output_path)
        if raw is _MISSING:
            return Score.fail(f"output has no {output_path}")
        try:
            got = _as_number(raw)
        except (TypeError, ValueError):
            return Score.fail(f"output is not a number: {raw!r}")
        ok = math.isclose(got, ref, rel_tol=rel_tol, abs_tol=abs_tol)
        reason = "" if ok else f"expected {ref} ± ({abs_tol} abs, {rel_tol} rel), got {got}"
        return Score.from_bool(ok, reason)

    return FunctionCheck(key, fn, kind=CheckKind.DETERMINISTIC)


def length(
    key: str = "length",
    *,
    max_chars: int | None = None,
    max_words: int | None = None,
    min_chars: int = 0,
) -> FunctionCheck:
    """The output text is non-empty (``min_chars``) and under the given limits."""

    def fn(sample: Sample, output: Output) -> Score:
        text = output.text.strip()
        chars, words = len(text), len(text.split())
        if chars < min_chars:
            return Score.fail(f"{chars} chars < min {min_chars}")
        if max_chars is not None and chars > max_chars:
            return Score.fail(f"{chars} chars > max {max_chars}")
        if max_words is not None and words > max_words:
            return Score.fail(f"{words} words > max {max_words}")
        return Score.ok()

    return FunctionCheck(key, fn, kind=CheckKind.DETERMINISTIC)


def python(
    fn: CheckFn,
    key: str | None = None,
    *,
    kind: CheckKind | str = CheckKind.DETERMINISTIC,
    version: int = 1,
) -> FunctionCheck:
    """Any ``fn(sample, output[, ctx]) -> Score | bool | float`` as a check, unregistered."""
    return FunctionCheck(key or fn.__name__, fn, kind=CheckKind(kind), version=version)


__all__ = ["contains", "exact", "json_schema", "length", "numeric_tolerance", "python", "regex"]
