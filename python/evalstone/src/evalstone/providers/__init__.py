"""Provider-blind model access for judges and prompt targets.

One canonical request shape (``ChatRequest``) and one response shape
(``ChatResponse``); thin adapters translate per provider. Model strings are
``<provider>/<model>``: ``openai/…`` (any OpenAI-compatible base URL — OpenAI,
OpenRouter, Ollama, vLLM), ``anthropic/…`` (official SDK), ``gemini/…``.
API keys come from the environment and are never stored.
"""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

# ── canonical shapes ──────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    system: str | None = None
    max_tokens: int = 1024
    temperature: float | None = None  # None → provider default; some providers reject it


class ChatResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None  # None = unpriced (unknown model)
    latency_ms: float = 0.0
    stop_reason: str | None = None
    raw: Any = None


class ProviderError(Exception):
    """A provider call failed (HTTP error, refusal, malformed response)."""


@runtime_checkable
class Provider(Protocol):
    name: str

    def complete(self, request: ChatRequest) -> ChatResponse: ...


# ── pricing (USD per 1M tokens: input, output) ────────────────────────────────

PRICES: dict[str, tuple[float, float]] = {
    # Anthropic — first-party rates (cached 2026-10)
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.0, 5.0),
    # Google — ai.google.dev/gemini-api/docs/pricing, paid tier, ≤200k (page dated 2026-10-09)
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.1-pro-preview": (2.00, 12.00),
    "gemini-3-flash-preview": (0.50, 3.00),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    # OpenAI: the published lineup changes often and the pricing page could not be read
    # by the tooling; add rows under `prices:` in evalstone.yaml (the gate warns when
    # a judge model is unpriced and max_cost_usd is set).
}


def price(
    model: str, input_tokens: int, output_tokens: int, table: dict | None = None
) -> float | None:
    """Cost in USD, or ``None`` when the model is not in the table (reported as unpriced)."""
    rates = (table or {}).get(model) or PRICES.get(model)
    if rates is None:
        return None
    return (input_tokens * rates[0] + output_tokens * rates[1]) / 1_000_000


# ── registry ──────────────────────────────────────────────────────────────────


ADAPTERS = ("openai", "anthropic", "gemini")


class ProviderConfig(BaseModel):
    # Which built-in adapter speaks to this provider; defaults to the entry's name, so
    # `openrouter: {adapter: openai, base_url: …}` and `openai: {…}` can coexist.
    adapter: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    api_key: str | None = Field(default=None, exclude=True, repr=False)
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: float = 60.0
    # OpenAI-compatible only: force "max_tokens" or "max_completion_tokens" (auto by host).
    max_tokens_param: str | None = None

    def resolve_key(self, default_env: str) -> str | None:
        if self.api_key:
            return self.api_key
        return os.environ.get(self.api_key_env or default_env)


DEFAULT_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


class Providers:
    """Resolves ``provider/model`` strings to adapters, lazily, with per-provider config."""

    def __init__(
        self,
        config: dict[str, ProviderConfig | dict[str, Any]] | None = None,
        *,
        default_model: str | None = None,
        prices: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self.config = {
            k: v if isinstance(v, ProviderConfig) else ProviderConfig(**v)
            for k, v in (config or {}).items()
        }
        self.default_model = default_model
        self.override_model: str | None = None  # wins over every judge's model when set
        self.prices = dict(prices or {})
        self._instances: dict[str, Provider] = {}

    def register(self, name: str, provider: Provider) -> None:
        """Install a provider instance under ``name`` (tests inject fakes this way)."""
        self._instances[name] = provider

    def close(self) -> None:
        """Close every adapter created so far (their HTTP clients) and forget them."""
        for provider in self._instances.values():
            close = getattr(provider, "close", None)
            if callable(close):
                close()
        self._instances.clear()

    def split(self, model: str | None) -> tuple[str, str]:
        model = self.override_model or model or self.default_model
        if not model:
            raise ProviderError("no model given and no judges.default_model configured")
        if "/" not in model:
            raise ProviderError(f"model must be '<provider>/<model>', got {model!r}")
        name, _, bare = model.partition("/")
        return name, bare

    def get(self, name: str) -> Provider:
        if name in self._instances:
            return self._instances[name]
        cfg = self.config.get(name)
        adapter = cfg.adapter if cfg and cfg.adapter else name
        if cfg is None and name not in ADAPTERS:
            known = sorted(set(ADAPTERS) | set(self.config))
            raise ProviderError(f"unknown provider {name!r} (known: {', '.join(known)})")
        cfg = cfg or ProviderConfig()
        if adapter == "openai":
            from evalstone.providers.openai_compat import OpenAICompatProvider

            self._instances[name] = OpenAICompatProvider(cfg, prices=self.prices)
        elif adapter == "anthropic":
            from evalstone.providers.anthropic_ import AnthropicProvider

            self._instances[name] = AnthropicProvider(cfg, prices=self.prices)
        elif adapter == "gemini":
            from evalstone.providers.gemini import GeminiProvider

            self._instances[name] = GeminiProvider(cfg, prices=self.prices)
        else:
            raise ProviderError(
                f"provider {name!r}: unknown adapter {adapter!r} (adapters: {', '.join(ADAPTERS)})"
            )
        return self._instances[name]
        cfg = self.config.get(name, ProviderConfig())
        if name == "openai":
            from evalstone.providers.openai_compat import OpenAICompatProvider

            self._instances[name] = OpenAICompatProvider(cfg, prices=self.prices)
        elif name == "anthropic":
            from evalstone.providers.anthropic_ import AnthropicProvider

            self._instances[name] = AnthropicProvider(cfg, prices=self.prices)
        elif name == "gemini":
            from evalstone.providers.gemini import GeminiProvider

            self._instances[name] = GeminiProvider(cfg, prices=self.prices)
        else:
            raise ProviderError(f"unknown provider {name!r} (known: openai, anthropic, gemini)")
        return self._instances[name]

    def complete(self, model: str | None, request_without_model: dict[str, Any]) -> ChatResponse:
        name, bare = self.split(model)
        return self.get(name).complete(ChatRequest(model=bare, **request_without_model))


__all__ = [
    "PRICES",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "Provider",
    "ProviderConfig",
    "ProviderError",
    "Providers",
    "price",
]
