"""Targets — what produces an ``Output`` for a sample.

``callable``: your function. ``http``: an endpoint. ``recorded``: outputs you
already have (offline runs, replays). A target never raises for one sample:
failures become ``Output.failed(...)`` so the rest of the run proceeds and the
failure is scored as an error.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx

from evalstone._json import dumps
from evalstone.dataset import Sample
from evalstone.output import Output


@runtime_checkable
class Target(Protocol):
    def describe(self) -> dict[str, Any]: ...

    def produce(self, sample: Sample) -> Output: ...


def _timed(fn: Callable[[], Any]) -> Output:
    started = time.perf_counter()
    try:
        value = fn()
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return Output.failed(f"{type(exc).__name__}: {exc}", latency_ms=elapsed)
    elapsed = (time.perf_counter() - started) * 1000
    if isinstance(value, Output):
        return value if value.latency_ms else value.model_copy(update={"latency_ms": elapsed})
    return Output(value=value, latency_ms=elapsed)


class CallableTarget:
    """``fn(sample.input) -> value | Output``; pass ``whole_sample=True`` to receive the Sample."""

    kind = "callable"

    def __init__(
        self, fn: Callable[[Any], Any], *, whole_sample: bool = False, name: str | None = None
    ):
        self._fn = fn
        self._whole = whole_sample
        self.name = name or getattr(fn, "__qualname__", repr(fn))

    def describe(self) -> dict[str, Any]:
        return {"kind": self.kind, "name": self.name}

    def produce(self, sample: Sample) -> Output:
        arg = sample if self._whole else sample.input
        return _timed(lambda: self._fn(arg))


class HttpTarget:
    """POST (by default) the sample input to ``url`` and read the JSON response.

    The request body is ``{"input": <sample.input>}`` unless ``body`` is given: a
    string leaf that is exactly ``"{input}"`` becomes the raw input (any JSON type);
    ``{input}`` inside a longer string is replaced by the input as text. For GET the
    input is sent as the ``input`` query parameter (JSON-encoded unless it is a
    string). ``response_path`` digs into the JSON response (dotted; digits index
    lists). One HTTP client is kept for the target's lifetime; call ``close()`` or
    use it as a context manager.
    """

    kind = "http"

    def __init__(
        self,
        url: str,
        *,
        method: str = "POST",
        headers: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
        response_path: str | None = None,
        timeout: float = 60.0,
        client: Any = None,
        name: str | None = None,
    ):
        self.url = url
        self.method = method.upper()
        self.headers = dict(headers or {})
        self.body = dict(body) if body else None
        self.response_path = response_path
        self.timeout = timeout
        self.name = name or url
        self._client = client
        self._owns_client = client is None

    def describe(self) -> dict[str, Any]:
        return {"kind": self.kind, "url": self.url, "method": self.method, "name": self.name}

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> HttpTarget:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _payload(self, sample: Sample) -> Any:
        if self.body is None:
            return {"input": sample.input}
        return _fill(self.body, sample.input)

    @staticmethod
    def _dig(data: Any, path: str) -> Any:
        for part in path.split("."):
            index_list = isinstance(data, list) and part.isdecimal()
            data = data[int(part)] if index_list else data[part]
        return data

    def produce(self, sample: Sample) -> Output:
        def call() -> Any:
            if self.method == "GET":
                value = sample.input if isinstance(sample.input, str) else dumps(sample.input)
                resp = self.client.get(self.url, params={"input": value}, headers=self.headers)
            else:
                resp = self.client.request(
                    self.method, self.url, json=self._payload(sample), headers=self.headers
                )
            resp.raise_for_status()
            data = resp.json()
            return self._dig(data, self.response_path) if self.response_path else data

        return _timed(call)


class RecordedTarget:
    """Outputs keyed by sample id — from a dict or a JSONL of ``{"id": ..., "output": ...}``."""

    kind = "recorded"

    def __init__(self, outputs: Mapping[str, Any] | str | Path, *, name: str | None = None):
        if isinstance(outputs, str | Path):
            path = Path(outputs)
            self.name = name or path.name
            loaded: dict[str, Any] = {}
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        row = json.loads(line)
                        loaded[row["id"]] = row["output"]
            self._outputs = loaded
        else:
            self.name = name or "recorded"
            self._outputs = dict(outputs)

    def describe(self) -> dict[str, Any]:
        return {"kind": self.kind, "name": self.name, "count": len(self._outputs)}

    def produce(self, sample: Sample) -> Output:
        if sample.id not in self._outputs:
            return Output.failed(f"no recorded output for sample {sample.id}")
        value = self._outputs[sample.id]
        if isinstance(value, dict) and "value" in value and set(value) <= set(Output.model_fields):
            return Output.model_validate(value)
        return Output(value=value)


def _fill(node: Any, value: Any) -> Any:
    """Substitute ``{input}`` in a body template: an exact leaf becomes the raw value,
    an embedded placeholder is replaced by the value as text."""
    if isinstance(node, dict):
        return {k: _fill(v, value) for k, v in node.items()}
    if isinstance(node, list):
        return [_fill(v, value) for v in node]
    if isinstance(node, str):
        if node == "{input}":
            return value
        if "{input}" in node:
            return node.replace("{input}", value if isinstance(value, str) else dumps(value))
    return node


def target(kind: str, **config: Any) -> Target:
    """Build a target from its ``kind`` and config (what ``evalstone.yaml`` holds)."""
    try:
        if kind == "callable":
            return CallableTarget(**config)
        if kind == "http":
            return HttpTarget(**config)
        if kind == "recorded":
            outputs = config.pop("outputs", None)
            path = config.pop("path", None)
            if outputs is None and path is None:
                raise ValueError("recorded target needs `outputs` or `path`")
            return RecordedTarget(outputs if outputs is not None else path, **config)
    except TypeError as exc:
        raise ValueError(f"{kind} target: {exc}") from None
    raise ValueError(f"unknown target kind {kind!r}")


__all__ = ["CallableTarget", "HttpTarget", "RecordedTarget", "Target", "target"]
