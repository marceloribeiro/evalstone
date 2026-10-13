"""The shared skeleton of the HTTP adapters: one persistent client, timing, and
the mapping of transport / status / body failures to ``ProviderError``."""

from __future__ import annotations

import time
from typing import Any

import httpx

from evalstone.providers import ProviderConfig, ProviderError


class HttpProvider:
    name = "http"

    def __init__(self, config: ProviderConfig, *, prices: dict | None = None, client: Any = None):
        self.base_url = (config.base_url or self.default_base_url).rstrip("/")
        # An entry named after its adapter (`openai:`) may fall back to the adapter's
        # default variable; a named entry (`openrouter: {adapter: openai}`) never does, so
        # one vendor's key is never sent to another.
        self.api_key = config.resolve_key("" if config.adapter else self.default_key_env)
        self.headers = dict(config.headers)
        self.timeout = config.timeout
        self.prices = prices or {}
        self._client = client
        self._owns_client = client is None

    default_base_url = ""
    default_key_env = ""

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def post_json(
        self, url: str, body: dict[str, Any], headers: dict[str, str]
    ) -> tuple[Any, float]:
        """POST ``body``; return ``(parsed JSON, latency_ms)`` or raise ``ProviderError``."""
        started = time.perf_counter()
        try:
            resp = self.client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: {type(exc).__name__}: {exc}") from exc
        latency = (time.perf_counter() - started) * 1000
        if resp.status_code >= 400:
            hint = (
                " (no API key is configured for this provider: set api_key_env)"
                if resp.status_code in (401, 403) and not self.api_key
                else ""
            )
            raise ProviderError(f"{self.name}: HTTP {resp.status_code}: {resp.text[:300]}{hint}")
        try:
            return resp.json(), latency
        except ValueError as exc:
            raise ProviderError(f"{self.name}: non-JSON response: {resp.text[:200]!r}") from exc


__all__ = ["HttpProvider"]
