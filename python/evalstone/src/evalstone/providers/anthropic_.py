"""Anthropic adapter — the official SDK (``pip install "evalstone[anthropic]"``)."""

from __future__ import annotations

import time
from typing import Any

from evalstone.providers import ChatRequest, ChatResponse, ProviderConfig, ProviderError, price


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, config: ProviderConfig, *, prices: dict | None = None, client: Any = None):
        self.prices = prices or {}
        if client is not None:
            self._client = client
            return
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ProviderError(
                "the anthropic provider needs the official SDK: pip install 'evalstone[anthropic]'"
            ) from exc
        kwargs: dict[str, Any] = {
            "timeout": config.timeout,
            "default_headers": config.headers or None,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        key = config.resolve_key("" if config.adapter else "ANTHROPIC_API_KEY")
        if key:
            # else the SDK resolves ANTHROPIC_API_KEY or an `ant auth login` profile itself
            kwargs["api_key"] = key
        self._client = anthropic.Anthropic(**kwargs)

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()

    def complete(self, request: ChatRequest) -> ChatResponse:
        import anthropic

        kwargs: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": [m.model_dump() for m in request.messages],
        }
        if request.system:
            kwargs["system"] = request.system
        # No `temperature`: current Claude models reject sampling parameters. No `thinking`
        # parameter either: the model default (adaptive where supported) applies.
        started = time.perf_counter()
        try:
            msg = self._client.messages.create(**kwargs)
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"anthropic: HTTP {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"anthropic: connection error: {exc}") from exc
        except (anthropic.AnthropicError, TypeError) as exc:
            # The SDK raises TypeError("Could not resolve authentication method…") when no
            # key is set; surface it as a provider error so the judge records a clean error.
            raise ProviderError(f"anthropic: {exc}") from exc
        latency = (time.perf_counter() - started) * 1000
        if msg.stop_reason == "refusal":
            details = getattr(msg, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise ProviderError(f"anthropic: refusal ({category or 'unspecified'})")
        text = "".join(block.text for block in msg.content if block.type == "text")
        inp, out = msg.usage.input_tokens, msg.usage.output_tokens
        return ChatResponse(
            text=text,
            model=msg.model,
            input_tokens=inp,
            output_tokens=out,
            cost_usd=price(request.model, inp, out, self.prices),
            latency_ms=latency,
            stop_reason=msg.stop_reason,
            raw=msg.to_dict(),
        )
