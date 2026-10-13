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
from typing import TYPE_CHECKING, Any

import jsonschema
from jsonschema.validators import validator_for

from evalstone.checks._base import CheckFn, FunctionCheck
from evalstone.score import CheckKind, Score

if TYPE_CHECKING:
    from evalstone.dataset import Sample
    from evalstone.output import Output

_MISSING = object()


def _dig(value: Any, path: str | None) -> Any:
    """Follow a dotted path into dicts/lists; ``_MISSING`` when absent."""
    if path is None:
        return value
    cur = value
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdecimal() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return _MISSING
    return cur


def _reference(sample: Sample, path: str | None, literal: Any) -> Any:
    if literal is not _MISSING:
        return literal
    ref = _dig(sample.expected, path)
    if ref is _MISSING or ref is None:
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
    *,
    key: str = "exact",
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
    *,
    key: str = "contains",
    needles: Iterable[str] | str = _MISSING,  # type: ignore[assignment]
    path: str | None = "must_include",
    require_all: bool = True,
    case_sensitive: bool = False,
) -> FunctionCheck:
    """Every (or any) needle appears in the output text. Needles default to
    ``sample.expected.must_include`` (a string or a list). An empty needle set
    passes vacuously."""
    literal: Any = _MISSING
    if needles is not _MISSING:  # materialise once: an iterator must not be consumed per sample
        literal = [needles] if isinstance(needles, str) else [str(n) for n in needles]

    def fn(sample: Sample, output: Output) -> Score:
        ref = _reference(sample, path, literal)
        wanted = [ref] if isinstance(ref, str) else [str(n) for n in ref]
        if not wanted:
            return Score.ok("no needles")
        hay = output.text if case_sensitive else output.text.lower()
        hits = [n for n in wanted if (n if case_sensitive else n.lower()) in hay]
        missing = [n for n in wanted if n not in hits]
        ok = not missing if require_all else bool(hits)
        value = len(hits) / len(wanted)
        reason = "" if ok else f"missing {missing!r}"
        return Score(value=value, passed=ok, reason=reason)

    return FunctionCheck(key, fn, kind=CheckKind.DETERMINISTIC)


def regex(
    pattern: str,
    *,
    key: str = "regex",
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


def json_schema(schema: dict[str, Any] | type, *, key: str = "json_schema") -> FunctionCheck:
    """The output is valid JSON and conforms to ``schema`` — a JSON Schema dict (the draft
    named by ``$schema``, 2020-12 when absent) or a pydantic model class. A malformed
    schema is rejected here, not once per sample at run time."""
    validate: Callable[[Any], None]
    if isinstance(schema, dict):
        cls = validator_for(schema, default=jsonschema.Draft202012Validator)
        try:
            cls.check_schema(schema)
        except jsonschema.SchemaError as exc:
            raise ValueError(f"json_schema {key!r}: invalid schema: {exc.message}") from None
        validator = cls(schema)

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
    *,
    key: str = "numeric_tolerance",
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
        if output_path is None:
            raw = output.value
        else:
            try:
                raw = _dig(_as_json(output), output_path)
            except json.JSONDecodeError as exc:
                return Score.fail(f"not valid JSON: {exc.msg}")
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
    *,
    key: str = "length",
    max_chars: int | None = None,
    max_words: int | None = None,
    min_chars: int = 0,
) -> FunctionCheck:
    """The output text is at least ``min_chars`` long (0 by default — pass ``min_chars=1``
    to reject empty output) and under the given limits."""

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
    """Any ``fn(sample, output[, ctx]) -> Score | bool | float`` as a check, unregistered.

    The key defaults to the function's name; lambdas, partials and callable
    objects have no usable name, so they need an explicit ``key``.
    """
    name = getattr(fn, "__name__", None)
    if key is None and (not name or name == "<lambda>"):
        raise ValueError("python(): give an explicit key for a lambda, partial or callable object")
    return FunctionCheck(key or name, fn, kind=CheckKind(kind), version=version)


__all__ = ["contains", "exact", "json_schema", "length", "numeric_tolerance", "python", "regex"]
