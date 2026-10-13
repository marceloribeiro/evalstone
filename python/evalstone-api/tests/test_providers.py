import httpx
import pytest
import respx

from app.config import get_settings
from app.errors import Invalid
from app.models import Provider
from app.services import providers as svc


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    """Resolve every hostname to a public address so the SSRF guard passes without the network."""
    monkeypatch.setattr(svc, "_resolve", lambda host: ["93.184.216.34"])


def _url(org):
    return f"/organizations/{org['id']}/providers"


def test_create_masks_the_key_and_lists(client, org):
    r = client.post(
        _url(org),
        json={
            "name": "openrouter",
            "adapter": "openai",
            "api_key": "sk-or-v1-secret-value-1234",
            "base_url": "https://openrouter.ai/api/v1/",
            "prices": {"x/model": [0.5, 1.5]},
        },
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert "api_key" not in out and "encrypted_api_key" not in out
    assert out["has_api_key"] is True and out["key_last4"] == "1234"
    assert out["base_url"] == "https://openrouter.ai/api/v1"  # trailing slash trimmed
    assert out["prices"] == {"x/model": [0.5, 1.5]}
    assert out["verified_ok"] is None
    listed = client.get(_url(org), headers=org["headers"]).json()
    assert [p["name"] for p in listed] == ["openrouter"]
    assert "secret" not in r.text and "secret" not in str(listed)


def test_name_unique_per_org_and_validated(client, org, register):
    body = {"name": "openai", "adapter": "openai", "api_key": "k"}
    assert client.post(_url(org), json=body, headers=org["headers"]).status_code == 201
    assert client.post(_url(org), json=body, headers=org["headers"]).status_code == 409
    bad = client.post(
        _url(org), json={"name": "Open AI", "adapter": "openai"}, headers=org["headers"]
    )
    assert bad.status_code == 422
    unknown = client.post(
        _url(org), json={"name": "x", "adapter": "cohere"}, headers=org["headers"]
    )
    assert unknown.status_code == 422
    other_h, _ = register("other@org.example.com")
    o2 = client.post("/organizations", json={"name": "Other"}, headers=other_h).json()
    assert (
        client.post(f"/organizations/{o2['id']}/providers", json=body, headers=other_h).status_code
        == 201
    )


def test_write_needs_admin_members_read_masked(client, org, register):
    member_h, _ = register("m@acme.example.com")
    client.post(
        f"/organizations/{org['id']}/invitations",
        json={"email": "m@acme.example.com"},
        headers=org["headers"],
    )
    body = {"name": "openai", "adapter": "openai", "api_key": "sk-live-abcd"}
    assert client.post(_url(org), json=body, headers=member_h).status_code == 403
    pid = client.post(_url(org), json=body, headers=org["headers"]).json()["id"]
    r = client.get(f"{_url(org)}/{pid}", headers=member_h)
    assert r.status_code == 200 and r.json()["key_last4"] == "abcd" and "sk-live" not in r.text
    assert (
        client.patch(f"{_url(org)}/{pid}", json={"timeout_s": 5}, headers=member_h).status_code
        == 403
    )
    assert client.delete(f"{_url(org)}/{pid}", headers=member_h).status_code == 403


def test_patch_key_semantics_absent_keeps_empty_clears(client, org, db):
    pid = client.post(
        _url(org),
        json={"name": "openai", "adapter": "openai", "api_key": "sk-first"},
        headers=org["headers"],
    ).json()["id"]
    row = db.get(Provider, __import__("uuid").UUID(pid))
    first_cipher = row.encrypted_api_key
    assert first_cipher and "sk-first" not in first_cipher
    r = client.patch(f"{_url(org)}/{pid}", json={"timeout_s": 10}, headers=org["headers"])
    assert r.status_code == 200 and r.json()["has_api_key"] is True and r.json()["timeout_s"] == 10
    db.expire_all()
    assert db.get(Provider, row.id).encrypted_api_key == first_cipher  # untouched
    r = client.patch(f"{_url(org)}/{pid}", json={"api_key": "sk-second"}, headers=org["headers"])
    assert r.json()["key_last4"] == "cond"
    r = client.patch(f"{_url(org)}/{pid}", json={"api_key": ""}, headers=org["headers"])
    assert r.json()["has_api_key"] is False and r.json()["key_last4"] is None


def test_delete_frees_the_name(client, org):
    body = {"name": "openai", "adapter": "openai"}
    pid = client.post(_url(org), json=body, headers=org["headers"]).json()["id"]
    assert client.delete(f"{_url(org)}/{pid}", headers=org["headers"]).status_code == 204
    assert client.get(f"{_url(org)}/{pid}", headers=org["headers"]).status_code == 404
    assert client.post(_url(org), json=body, headers=org["headers"]).status_code == 201


@pytest.mark.parametrize(
    "url",
    [
        "ftp://x.example.com",
        "http://localhost:11434",
        "http://api.localhost",
        "http://metadata.google.internal/computeMetadata",
        "http://169.254.169.254/latest",
        "http://127.0.0.1:8000",
        "http://10.0.0.5/v1",
        "http://[::1]/v1",
        "https://user:pw@x.example.com/v1",
        "not a url",
    ],
)
def test_base_url_ssrf_guard_rejects(url):
    with pytest.raises(Invalid):
        svc.validate_base_url(url)


def test_base_url_guard_follows_dns(monkeypatch):
    monkeypatch.setattr(svc, "_resolve", lambda host: ["192.168.1.10"])
    with pytest.raises(Invalid, match="private or reserved"):
        svc.validate_base_url("https://evil.example.com/v1")
    monkeypatch.setattr(svc, "_resolve", lambda host: ["93.184.216.34"])
    assert svc.validate_base_url("https://good.example.com/v1/") == "https://good.example.com/v1"
    assert svc.validate_base_url("  ") is None


def test_private_urls_allowed_when_the_operator_opts_in(monkeypatch):
    monkeypatch.setattr(get_settings(), "provider_allow_private_urls", True)
    assert svc.validate_base_url("http://localhost:11434/v1") == "http://localhost:11434/v1"


def test_prices_validated(client, org):
    bad = client.post(
        _url(org),
        json={"name": "x", "adapter": "openai", "prices": {"m": [1]}},
        headers=org["headers"],
    )
    assert bad.status_code == 422


@respx.mock
def test_test_endpoint_makes_one_call_with_the_decrypted_key(client, org, db):
    pid = client.post(
        _url(org),
        json={
            "name": "openrouter",
            "adapter": "openai",
            "api_key": "sk-or-secret",
            "base_url": "https://openrouter.example.com/api/v1",
            "headers": {"HTTP-Referer": "https://evalstone.com"},
            "prices": {"meta/llama": [1.0, 2.0]},
        },
        headers=org["headers"],
    ).json()["id"]
    route = respx.post("https://openrouter.example.com/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "meta/llama",
                "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 1},
            },
        )
    )
    r = client.post(f"{_url(org)}/{pid}/test", json={"model": "meta/llama"}, headers=org["headers"])
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["input_tokens"] == 10 and out["output_tokens"] == 1
    assert out["cost_usd"] == pytest.approx((10 * 1.0 + 1 * 2.0) / 1_000_000)
    assert route.call_count == 1
    sent = route.calls[0].request
    assert sent.headers["Authorization"] == "Bearer sk-or-secret"  # decrypted in-process only
    assert sent.headers["HTTP-Referer"] == "https://evalstone.com"
    assert b'"max_tokens": 5' in sent.content or b'"max_tokens":5' in sent.content
    row = client.get(f"{_url(org)}/{pid}", headers=org["headers"]).json()
    assert row["verified_ok"] is True and row["last_verified_at"] and row["last_error"] is None


@respx.mock
def test_test_endpoint_reports_failures_without_a_500(client, org):
    pid = client.post(
        _url(org),
        json={
            "name": "openai",
            "adapter": "openai",
            "api_key": "sk-bad",
            "base_url": "https://api.example.com/v1",
        },
        headers=org["headers"],
    ).json()["id"]
    respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": {"message": "Incorrect API key"}})
    )
    r = client.post(f"{_url(org)}/{pid}/test", json={"model": "gpt-x"}, headers=org["headers"])
    assert r.status_code == 200
    assert r.json()["ok"] is False and "401" in r.json()["error"]
    row = client.get(f"{_url(org)}/{pid}", headers=org["headers"]).json()
    assert row["verified_ok"] is False and "401" in row["last_error"]


def test_test_endpoint_undecryptable_key_is_422(client, org, monkeypatch):
    from cryptography.fernet import Fernet

    from app import crypto

    pid = client.post(
        _url(org),
        json={"name": "openai", "adapter": "openai", "api_key": "sk-x"},
        headers=org["headers"],
    ).json()["id"]
    monkeypatch.setattr(crypto, "_fernet", lambda: Fernet(Fernet.generate_key()))
    r = client.post(f"{_url(org)}/{pid}/test", json={"model": "m"}, headers=org["headers"])
    assert r.status_code == 422 and "PROVIDER_CREDS_KEY" in r.json()["detail"]


def test_registry_never_falls_back_to_server_env(db, org, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "server-key-must-not-leak")
    from uuid import UUID

    from app.services import organizations as org_svc

    o = org_svc.get_organization(db, UUID(org["id"]))
    p = svc.create(db, org=o, name="openai", adapter="openai")  # keyless entry
    registry = svc.build_registry([p])
    try:
        assert registry.get("openai").api_key is None  # the adapter did not read OPENAI_API_KEY
    finally:
        registry.close()


# --- regressions from the #26 review ---------------------------------------------------------


def test_keyless_anthropic_entry_never_uses_the_server_key(client, org, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "server-key-must-not-leak")
    pid = client.post(
        _url(org), json={"name": "anthropic", "adapter": "anthropic"}, headers=org["headers"]
    ).json()["id"]
    r = client.post(f"{_url(org)}/{pid}/test", json={"model": "claude-x"}, headers=org["headers"])
    assert r.status_code == 422 and "no API key" in r.json()["detail"]
    row = client.get(f"{_url(org)}/{pid}", headers=org["headers"]).json()
    assert row["verified_ok"] is None  # nothing was called, nothing was recorded


@pytest.mark.parametrize("url", ["http://[", "http://[::1", "http://" + "a" * 70 + ".example.com"])
def test_malformed_base_url_is_422_not_500(client, org, url, monkeypatch):
    monkeypatch.setattr(svc, "_resolve", svc._getaddrinfo)  # real resolver: over-long label
    r = client.post(
        _url(org), json={"name": "x", "adapter": "openai", "base_url": url}, headers=org["headers"]
    )
    assert r.status_code == 422, r.text


def test_slow_dns_is_bounded(monkeypatch):
    import importlib
    import time

    real_resolve = importlib.reload(svc)._resolve  # undo the autouse patch for this test
    monkeypatch.setattr(svc, "_resolve", real_resolve)
    monkeypatch.setattr(svc, "RESOLVE_TIMEOUT_S", 0.05)
    monkeypatch.setattr(svc, "_getaddrinfo", lambda host: time.sleep(1) or ["93.184.216.34"])
    with pytest.raises(Invalid, match="did not resolve within"):
        svc.validate_base_url("https://slow.example.com/v1")


def test_short_keys_get_no_last4_hint(client, org):
    r = client.post(
        _url(org),
        json={"name": "proxy", "adapter": "openai", "api_key": "abcd"},
        headers=org["headers"],
    )
    assert r.json()["has_api_key"] is True and r.json()["key_last4"] is None
    assert "abcd" not in r.text


def test_delete_purges_the_key_and_refuses_while_judge_settings_use_it(client, project, db):
    import uuid

    org, h = project["org"], project["headers"]
    pid = client.post(
        _url(org),
        json={"name": "openai", "adapter": "openai", "api_key": "sk-live-1234"},
        headers=h,
    ).json()["id"]
    assert (
        client.put(
            f"/projects/{project['id']}/judge-settings",
            json={"default_model": "openai/x"},
            headers=h,
        ).status_code
        == 200
    )
    blocked = client.delete(f"{_url(org)}/{pid}", headers=h)
    assert blocked.status_code == 409 and "rag-bot" in blocked.json()["detail"]
    client.put(f"/projects/{project['id']}/judge-settings", json={}, headers=h)
    assert client.delete(f"{_url(org)}/{pid}", headers=h).status_code == 204
    row = db.get(Provider, uuid.UUID(pid))
    assert row.deleted_at is not None and row.encrypted_api_key is None and row.key_last4 is None


def test_each_provider_is_costed_at_its_own_price_table(db, org):
    from uuid import UUID

    from app.services import organizations as org_svc

    o = org_svc.get_organization(db, UUID(org["id"]))
    a = svc.create(db, org=o, name="openai", adapter="openai", prices={"gpt-x": [2.5, 10.0]})
    b = svc.create(db, org=o, name="openrouter", adapter="openai", prices={"gpt-x": [3.0, 12.0]})
    registry = svc.build_registry([a, b])
    try:
        assert registry.get("openai").prices["gpt-x"] == (2.5, 10.0)
        assert registry.get("openrouter").prices["gpt-x"] == (3.0, 12.0)
    finally:
        registry.close()


def test_patch_clears_max_tokens_param_and_resets_the_verdict(client, org, db):
    import uuid

    pid = client.post(
        _url(org),
        json={"name": "openai", "adapter": "openai", "max_tokens_param": "max_tokens"},
        headers=org["headers"],
    ).json()["id"]
    row = db.get(Provider, uuid.UUID(pid))

    def mark_verified():
        db.refresh(row)  # the API wrote through another session
        row.verified_ok = True
        db.commit()

    mark_verified()
    r = client.patch(f"{_url(org)}/{pid}", json={"max_tokens_param": None}, headers=org["headers"])
    assert r.json()["max_tokens_param"] is None and r.json()["verified_ok"] is None
    row.verified_ok = True
    db.commit()
    r = client.patch(
        f"{_url(org)}/{pid}", json={"headers": {"X-Auth": "new"}}, headers=org["headers"]
    )
    assert r.json()["verified_ok"] is None  # new headers = different credentials
    mark_verified()
    r = client.patch(f"{_url(org)}/{pid}", json={"prices": {"m": [1, 1]}}, headers=org["headers"])
    assert r.json()["verified_ok"] is True  # prices do not affect the call
