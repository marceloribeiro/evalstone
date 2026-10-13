import httpx
import pytest
import respx
from evalstone.providers import ChatResponse

from app.services import model_proxy as svc
from app.services import providers as provider_svc

UPSTREAM = "https://judge.example.com/v1"


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(provider_svc, "_resolve", lambda host: ["93.184.216.34"])


@pytest.fixture
def judged(client, project):
    """A provider `judge` with a key + prices and judge settings routing `helpful` to it."""
    org, h = project["org"], project["headers"]
    client.post(
        f"/organizations/{org['id']}/providers",
        json={
            "name": "judge",
            "adapter": "openai",
            "api_key": "sk-judge-secret",
            "base_url": UPSTREAM,
            "prices": {"small": [1.0, 2.0]},
        },
        headers=h,
    )
    client.post(
        f"/organizations/{org['id']}/providers",
        json={"name": "other", "adapter": "openai"},
        headers=h,
    )
    r = client.put(
        f"/projects/{project['id']}/judge-settings",
        json={"default_model": "judge/small", "overrides": {"strict": "other/big"}},
        headers=h,
    )
    assert r.status_code == 200
    return project


def _ok(text="4 - fine"):
    return httpx.Response(
        200,
        json={
            "model": "small",
            "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 5},
        },
    )


BODY = {
    "check_key": "helpful",
    "system": "You grade answers 1-5.",
    "messages": [{"role": "user", "content": "INPUT: q\nOUTPUT: a"}],
    "max_tokens": 64,
}


@respx.mock
def test_complete_resolves_the_judge_model_and_returns_the_library_response(client, judged, db):
    route = respx.post(UPSTREAM + "/chat/completions").mock(return_value=_ok())
    r = client.post(
        f"/projects/{judged['id']}/model/complete", json=BODY, headers=judged["headers"]
    )
    assert r.status_code == 200, r.text
    out = r.json()
    resp = ChatResponse.model_validate(out)  # the library's shape
    assert resp.text == "4 - fine" and resp.input_tokens == 100 and resp.output_tokens == 5
    assert resp.cost_usd == pytest.approx((100 * 1.0 + 5 * 2.0) / 1_000_000)
    assert "raw" not in out
    sent = route.calls[0].request
    assert sent.headers["Authorization"] == "Bearer sk-judge-secret"  # decrypted in-process only
    body = sent.content.decode()
    assert '"model": "small"' in body.replace('":"', '": "') and "You grade" in body
    calls = client.get(f"/projects/{judged['id']}/model/calls", headers=judged["headers"]).json()
    assert calls["total"] == 1 and calls["items"][0]["ok"] is True
    assert (
        calls["items"][0]["check_key"] == "helpful"
        and calls["items"][0]["provider_name"] == "judge"
    )
    assert (
        calls["usage"]["cost_usd"] == pytest.approx(resp.cost_usd) and calls["usage"]["calls"] == 1
    )


@respx.mock
def test_explicit_model_beats_settings_and_overrides_apply(client, judged):
    respx.post(UPSTREAM + "/chat/completions").mock(return_value=_ok())
    h = judged["headers"]
    url = f"/projects/{judged['id']}/model/complete"
    r = client.post(url, json={**BODY, "model": "judge/small", "check_key": "strict"}, headers=h)
    assert r.status_code == 200  # explicit model wins over the `strict` override
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": {"message": "no key"}})
    )
    r = client.post(url, json={**BODY, "check_key": "strict"}, headers=h)
    assert r.status_code == 502 and "other" in r.json()["detail"]  # the override routed to `other`
    calls = client.get(f"/projects/{judged['id']}/model/calls", headers=h).json()["items"]
    assert [c["provider_name"] for c in calls] == ["other", "judge"]


def test_unresolvable_model_is_422(client, project):
    h = project["headers"]
    url = f"/projects/{project['id']}/model/complete"
    r = client.post(url, json=BODY, headers=h)
    assert r.status_code == 422 and "no judge model" in r.json()["detail"]
    r = client.post(url, json={**BODY, "model": "nope/x"}, headers=h)
    assert r.status_code == 422 and "no provider named 'nope'" in r.json()["detail"]
    r = client.post(url, json={**BODY, "model": "bare"}, headers=h)
    assert r.status_code == 422
    r = client.post(url, json={**BODY, "check_key": None}, headers=h)
    assert r.status_code == 422 and "give a model" in r.json()["detail"]


@respx.mock
def test_upstream_failure_is_502_and_metered(client, judged):
    respx.post(UPSTREAM + "/chat/completions").mock(
        return_value=httpx.Response(429, json={"error": {"message": "rate limited"}})
    )
    r = client.post(
        f"/projects/{judged['id']}/model/complete", json=BODY, headers=judged["headers"]
    )
    assert r.status_code == 502 and "429" in r.json()["detail"]
    calls = client.get(f"/projects/{judged['id']}/model/calls", headers=judged["headers"]).json()
    assert (
        calls["total"] == 1
        and calls["items"][0]["ok"] is False
        and "429" in calls["items"][0]["error"]
    )
    assert calls["usage"] == {
        "calls": 1,
        "failed": 1,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "unpriced_calls": 0,
    }


@respx.mock
def test_ingest_key_can_call_and_is_metered_without_a_user(client, judged):
    respx.post(UPSTREAM + "/chat/completions").mock(return_value=_ok())
    h = judged["headers"]
    secret = client.post(
        f"/projects/{judged['id']}/ingest-keys", json={"name": "ci"}, headers=h
    ).json()["key"]
    kh = {"Authorization": f"Bearer {secret}"}
    assert (
        client.post(f"/projects/{judged['id']}/model/complete", json=BODY, headers=kh).status_code
        == 200
    )
    calls = client.get(f"/projects/{judged['id']}/model/calls", headers=kh).json()
    assert calls["items"][0]["caller_user_id"] is None


def test_request_limits(client, judged):
    h = judged["headers"]
    url = f"/projects/{judged['id']}/model/complete"
    assert (
        client.post(
            url, json={**BODY, "max_tokens": svc.MAX_OUTPUT_TOKENS + 1}, headers=h
        ).status_code
        == 422
    )
    huge = {**BODY, "messages": [{"role": "user", "content": "x" * (svc.MAX_REQUEST_BYTES + 1)}]}
    r = client.post(url, json=huge, headers=h)
    assert r.status_code == 422 and "bytes" in r.json()["detail"]
    assert client.post(url, json={**BODY, "messages": []}, headers=h).status_code == 422


def test_unpriced_calls_are_counted(client, judged, db):
    with respx.mock:
        respx.post(UPSTREAM + "/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "model": "unknown-model",
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )
        )
        r = client.post(
            f"/projects/{judged['id']}/model/complete",
            json={**BODY, "model": "judge/unknown-model"},
            headers=judged["headers"],
        )
    assert r.status_code == 200 and r.json()["cost_usd"] is None
    usage = client.get(f"/projects/{judged['id']}/model/calls", headers=judged["headers"]).json()[
        "usage"
    ]
    assert usage["unpriced_calls"] == 1 and usage["cost_usd"] == 0.0
