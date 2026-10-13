"""OpenAI-compatible Chat Completions adapter (OpenAI, OpenRouter, Ollama, vLLM, …).

api.openai.com's current models reject ``max_tokens`` in favour of
``max_completion_tokens``; compatible servers mostly still want ``max_tokens``.
The parameter name is picked from the host and can be forced with
``ProviderConfig(max_tokens_param=...)``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from evalstone.providers import ChatRequest, ChatResponse, ProviderConfig, ProviderError, price
from evalstone.providers._http import HttpProvider

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAICompatProvider(HttpProvider):
    name = "openai"
    default_base_url = DEFAULT_BASE_URL
    default_key_env = "OPENAI_API_KEY"

    def __init__(self, config: ProviderConfig, *, prices: dict | None = None, client: Any = None):
        super().__init__(config, prices=prices, client=client)
        host = urlparse(self.base_url).hostname or ""
        self.max_tokens_param = config.max_tokens_param or (
            "max_completion_tokens" if host.endswith("openai.com") else "max_tokens"
        )

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
            self.max_tokens_param: request.max_tokens,
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        data, latency = self.post_json(f"{self.base_url}/chat/completions", body, self._headers())
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
