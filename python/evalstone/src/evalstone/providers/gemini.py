"""Gemini adapter — Generative Language API ``generateContent`` over HTTP."""

from __future__ import annotations

import time
from typing import Any

import httpx

from evalstone.providers import ChatRequest, ChatResponse, ProviderConfig, ProviderError, price

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    name = "gemini"

    def __init__(self, config: ProviderConfig, *, prices: dict | None = None, client: Any = None):
        self.base_url = (config.base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = config.resolve_key("GEMINI_API_KEY")
        self.headers = dict(config.headers)
        self.timeout = config.timeout
        self.prices = prices or {}
        self._client = client

    def complete(self, request: ChatRequest) -> ChatResponse:
        body: dict[str, Any] = {
            "contents": [
                {
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                }
                for m in request.messages
            ],
            "generationConfig": {"maxOutputTokens": request.max_tokens},
        }
        if request.system:
            body["systemInstruction"] = {"parts": [{"text": request.system}]}
        if request.temperature is not None:
            body["generationConfig"]["temperature"] = request.temperature
        headers = {"Content-Type": "application/json", **self.headers}
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key
        url = f"{self.base_url}/models/{request.model}:generateContent"
        client = self._client or httpx.Client(timeout=self.timeout)
        started = time.perf_counter()
        try:
            resp = client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"gemini: {type(exc).__name__}: {exc}") from exc
        finally:
            if self._client is None:
                client.close()
        latency = (time.perf_counter() - started) * 1000
        if resp.status_code >= 400:
            raise ProviderError(f"gemini: HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            candidate = data["candidates"][0]
            parts = candidate.get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"gemini: malformed response: {data!r}"[:400]) from exc
        usage = data.get("usageMetadata") or {}
        inp, out = int(usage.get("promptTokenCount", 0)), int(usage.get("candidatesTokenCount", 0))
        return ChatResponse(
            text=text,
            model=data.get("modelVersion") or request.model,
            input_tokens=inp,
            output_tokens=out,
            cost_usd=price(request.model, inp, out, self.prices),
            latency_ms=latency,
            stop_reason=candidate.get("finishReason"),
            raw=data,
        )
