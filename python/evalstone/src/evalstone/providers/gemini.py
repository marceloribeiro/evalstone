"""Gemini adapter — Generative Language API ``generateContent`` over HTTP."""

from __future__ import annotations

from typing import Any

from evalstone.providers import ChatRequest, ChatResponse, ProviderError, price
from evalstone.providers._http import HttpProvider

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(HttpProvider):
    name = "gemini"
    default_base_url = DEFAULT_BASE_URL
    default_key_env = "GEMINI_API_KEY"

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
        data, latency = self.post_json(url, body, headers)
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
