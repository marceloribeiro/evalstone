import json

import anthropic
import httpx
import httpx2
import pytest

from evalstone.providers import (
    PRICES,
    ChatMessage,
    ChatRequest,
    ProviderConfig,
    ProviderError,
    Providers,
    price,
)
from evalstone.providers.anthropic_ import AnthropicProvider
from evalstone.providers.gemini import GeminiProvider
from evalstone.providers.openai_compat import OpenAICompatProvider

REQ = ChatRequest(
    model="m", system="be terse", messages=[ChatMessage(role="user", content="hi")], max_tokens=50
)


def test_price_table_and_unknown_models():
    assert price("claude-haiku-5-5", 1_000_000, 0) == PRICES["claude-haiku-5-5"][0]
    assert price("claude-opus-5-5", 1000, 1000) == pytest.approx((4.0 + 20.0) / 1000)
    assert price("gpt-something", 10, 10) is None
    assert price("gpt-something", 1_000_000, 0, {"gpt-something": (1.0, 2.0)}) == 1.0


def test_openai_compat_adapter_shapes_request_and_reads_usage():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "m-2026",
                "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            },
        )

    cfg = ProviderConfig(base_url="https://openrouter.ai/api/v1/", api_key="sk-test")
    prov = OpenAICompatProvider(cfg, client=httpx.Client(transport=httpx.MockTransport(handler)))
    resp = prov.complete(REQ)
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "be terse"}
    assert seen["body"]["max_tokens"] == 50 and "temperature" not in seen["body"]
    assert resp.text == "hello" and resp.model == "m-2026" and resp.stop_reason == "stop"
    assert (resp.input_tokens, resp.output_tokens) == (10, 2) and resp.cost_usd is None
    assert resp.latency_ms > 0


def test_openai_compat_http_errors_and_malformed_bodies_raise_provider_error():
    def mocked(handler):
        return httpx.Client(transport=httpx.MockTransport(handler))

    client = mocked(lambda r: httpx.Response(429, text="slow down"))
    with pytest.raises(ProviderError, match="HTTP 429"):
        OpenAICompatProvider(ProviderConfig(), client=client).complete(REQ)
    client = mocked(lambda r: httpx.Response(200, json={"oops": 1}))
    with pytest.raises(ProviderError, match="malformed"):
        OpenAICompatProvider(ProviderConfig(), client=client).complete(REQ)


def _anthropic_client(handler):
    return anthropic.Anthropic(
        api_key="test",
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )


def test_anthropic_adapter_uses_the_sdk_and_prices_known_models():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [{"type": "text", "text": "hello"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
            },
        )

    prov = AnthropicProvider(ProviderConfig(), client=_anthropic_client(handler))
    resp = prov.complete(REQ.model_copy(update={"model": "claude-haiku-5-5"}))
    assert seen["body"]["system"] == "be terse" and seen["body"]["max_tokens"] == 50
    assert "temperature" not in seen["body"] and "thinking" not in seen["body"]
    assert resp.text == "hello" and resp.cost_usd == pytest.approx(0.10)


def test_anthropic_refusal_and_http_errors_raise_provider_error():
    def refusal(request):
        return httpx2.Response(
            200,
            json={
                "id": "msg_2",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [],
                "stop_reason": "refusal",
                "stop_sequence": None,
                "stop_details": {"type": "refusal", "category": "cyber", "explanation": "no"},
                "usage": {"input_tokens": 1, "output_tokens": 0},
            },
        )

    with pytest.raises(ProviderError, match=r"refusal \(cyber\)"):
        AnthropicProvider(ProviderConfig(), client=_anthropic_client(refusal)).complete(REQ)

    def bad(request):
        err = {"type": "invalid_request_error", "message": "nope"}
        return httpx2.Response(400, json={"type": "error", "error": err})

    with pytest.raises(ProviderError, match="HTTP 400"):
        AnthropicProvider(ProviderConfig(), client=_anthropic_client(bad)).complete(REQ)


def test_gemini_adapter_shapes_request_and_reads_usage():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "hel"}, {"text": "lo"}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3},
                "modelVersion": "gemini-x",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    prov = GeminiProvider(ProviderConfig(api_key="g-key"), client=client)
    resp = prov.complete(REQ.model_copy(update={"model": "gemini-x"}))
    assert seen["url"].endswith("/models/gemini-x:generateContent") and seen["key"] == "g-key"
    assert seen["body"]["systemInstruction"] == {"parts": [{"text": "be terse"}]}
    assert seen["body"]["contents"] == [{"role": "user", "parts": [{"text": "hi"}]}]
    assert resp.text == "hello" and (resp.input_tokens, resp.output_tokens) == (5, 3)


def test_registry_splits_model_strings_resolves_keys_from_env_and_accepts_fakes(monkeypatch):
    monkeypatch.setenv("MY_KEY", "from-env")
    cfg = {"openai": {"api_key_env": "MY_KEY", "base_url": "http://x/v1"}}
    reg = Providers(cfg, default_model="openai/gpt")
    assert reg.split(None) == ("openai", "gpt")
    assert reg.split("anthropic/claude-haiku-5-5") == ("anthropic", "claude-haiku-5-5")
    with pytest.raises(ProviderError, match="<provider>/<model>"):
        reg.split("gpt")
    with pytest.raises(ProviderError, match="unknown provider"):
        reg.get("cohere")
    assert reg.get("openai").api_key == "from-env"
    assert Providers().split("openai/x") == ("openai", "x")
    with pytest.raises(ProviderError, match="no model given"):
        Providers().split(None)

    class Fake:
        name = "openai"

        def complete(self, request):
            from evalstone.providers import ChatResponse

            return ChatResponse(text=f"echo:{request.messages[0].content}", model=request.model)

    reg.register("openai", Fake())
    echoed = reg.complete(None, {"messages": [ChatMessage(role="user", content="x")]})
    assert echoed.text == "echo:x"


def test_anthropic_missing_key_is_a_provider_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    prov = AnthropicProvider(ProviderConfig(api_key_env="EVALSTONE_TEST_NO_SUCH_KEY"))
    with pytest.raises(ProviderError, match="anthropic: "):
        prov.complete(REQ.model_copy(update={"model": "claude-haiku-5-5"}))
