"""OpenAI-compatible Chat Completions adapter (OpenAI, OpenRouter, Ollama, vLLM, …)."""

from __future__ import annotations

import time
from typing import Any

import httpx

from evalstone.providers import ChatRequest, ChatResponse, ProviderConfig, ProviderError, price

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAICompatProvider:
    name = "openai"

    def __init__(self, config: ProviderConfig, *, prices: dict | None = None, client: Any = None):
        self.base_url = (config.base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = config.resolve_key("OPENAI_API_KEY")
        self.headers = dict(config.headers)
        self.timeout = config.timeout
        self.prices = prices or {}
        self._client = client

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", **self.headers}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def complete(self, request: ChatRequest) -> ChatResponse:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages += [m.model_dump() for m in request.messages]
        body: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        client = self._client or httpx.Client(timeout=self.timeout)
        started = time.perf_counter()
        try:
            resp = client.post(
                f"{self.base_url}/chat/completions", json=body, headers=self._headers()
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"openai: {type(exc).__name__}: {exc}") from exc
        finally:
            if self._client is None:
                client.close()
        latency = (time.perf_counter() - started) * 1000
        if resp.status_code >= 400:
            raise ProviderError(f"openai: HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"openai: malformed response: {data!r}"[:400]) from exc
        usage = data.get("usage") or {}
        inp, out = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        return ChatResponse(
            text=text,
            model=data.get("model") or request.model,
            input_tokens=inp,
            output_tokens=out,
            cost_usd=price(request.model, inp, out, self.prices),
            latency_ms=latency,
            stop_reason=choice.get("finish_reason"),
            raw=data,
        )
