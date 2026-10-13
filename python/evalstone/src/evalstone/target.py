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

    The request body is ``{"input": <sample.input>}`` unless ``body`` is given, in
    which case ``{input}`` placeholders in its JSON text are filled. ``response_path``
    digs into the JSON response for the output value.
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
    ):
        self.url = url
        self.method = method.upper()
        self.headers = dict(headers or {})
        self.body = dict(body) if body else None
        self.response_path = response_path
        self.timeout = timeout
        self._client = client

    def describe(self) -> dict[str, Any]:
        return {"kind": self.kind, "url": self.url, "method": self.method}

    def _payload(self, sample: Sample) -> Any:
        if self.body is None:
            return {"input": sample.input}
        text = json.dumps(self.body)
        return json.loads(text.replace('"{input}"', json.dumps(sample.input)))

    def produce(self, sample: Sample) -> Output:
        import httpx

        def call() -> Any:
            client = self._client or httpx.Client(timeout=self.timeout)
            try:
                if self.method == "GET":
                    resp = client.get(
                        self.url, params={"input": sample.input}, headers=self.headers
                    )
                else:
                    resp = client.request(
                        self.method, self.url, json=self._payload(sample), headers=self.headers
                    )
                resp.raise_for_status()
                data = resp.json()
            finally:
                if self._client is None:
                    client.close()
            if self.response_path:
                for part in self.response_path.split("."):
                    data = data[part]
            return data

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


def target(kind: str, **config: Any) -> Target:
    """Build a target from its ``kind`` and config (what ``evalstone.yaml`` holds)."""
    if kind == "callable":
        return CallableTarget(config["fn"], whole_sample=config.get("whole_sample", False))
    if kind == "http":
        return HttpTarget(**config)
    if kind == "recorded":
        return RecordedTarget(config["outputs"] if "outputs" in config else config["path"])
    raise ValueError(f"unknown target kind {kind!r}")


__all__ = ["CallableTarget", "HttpTarget", "RecordedTarget", "Target", "target"]
