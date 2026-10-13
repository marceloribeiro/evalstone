"""The center attach: the proxy as a Providers, the center as a ScoreCache, labels, run push."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from evalstone.center import CenterCache, CenterClient, CenterConfig, CenterError, CenterProviders
from evalstone.checks.human import human, output_hash
from evalstone.checks.judge import judge
from evalstone.config import Config
from evalstone.dataset import Sample
from evalstone.output import Output
from evalstone.providers import ChatMessage, ProviderError
from evalstone.score import Context, Score

URL = "http://center.test"
PROJECT = "11111111-2222-4333-8444-555555555555"
P = f"{URL}/projects/{PROJECT}"


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setenv("EVALSTONE_API_KEY", "es_test_key")
    return CenterConfig(url=URL + "/", project=PROJECT)


def _verdict(text='{"score": 4, "reason": "fine"}', model="small"):
    return httpx.Response(
        200,
        json={
            "text": text,
            "model": model,
            "input_tokens": 10,
            "output_tokens": 2,
            "cost_usd": 0.00001,
            "latency_ms": 12.5,
            "stop_reason": "stop",
        },
    )


def test_client_needs_a_key(monkeypatch):
    monkeypatch.delenv("EVALSTONE_API_KEY", raising=False)
    with pytest.raises(CenterError, match="EVALSTONE_API_KEY"):
        CenterClient(CenterConfig(url=URL, project=PROJECT))


@respx.mock
def test_providers_complete_posts_the_proxy_body_with_the_bearer(cfg):
    route = respx.post(f"{P}/model/complete").mock(return_value=_verdict())
    providers = CenterProviders(CenterClient(cfg), default_model="judge/small")
    resp = providers.complete(
        None,
        {"system": "Grade.", "messages": [ChatMessage(role="user", content="x")], "max_tokens": 5},
    )
    assert resp.text.startswith('{"score": 4') and resp.cost_usd == pytest.approx(0.00001)
    sent = route.calls[0].request
    assert sent.headers["Authorization"] == "Bearer es_test_key"
    body = json.loads(sent.content)
    assert body["model"] == "judge/small" and body["system"] == "Grade." and body["max_tokens"] == 5
    assert body["messages"] == [{"role": "user", "content": "x"}]
    assert providers.split("other/big") == ("other", "big")
    with pytest.raises(ProviderError, match="<provider>/<model>"):
        providers.split("bare")
    with pytest.raises(ProviderError, match="default judge model"):
        CenterProviders(CenterClient(cfg)).split(None)


@respx.mock
def test_center_errors_become_provider_errors(cfg):
    respx.post(f"{P}/model/complete").mock(
        return_value=httpx.Response(502, json={"detail": "provider 'judge' failed: HTTP 401"})
    )
    providers = CenterProviders(CenterClient(cfg))
    with pytest.raises(ProviderError, match="HTTP 502: provider 'judge' failed"):
        providers.complete("judge/small", {"messages": [ChatMessage(role="user", content="x")]})
    respx.post(f"{P}/model/complete").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ProviderError, match="ConnectError"):
        providers.complete("judge/small", {"messages": [ChatMessage(role="user", content="x")]})


@respx.mock
def test_cache_get_set_and_tolerance(cfg):
    key = "a" * 64
    get = respx.get(f"{P}/judge-cache/{key}").mock(return_value=httpx.Response(404))
    put = respx.put(f"{P}/judge-cache/{key}").mock(return_value=httpx.Response(201, json={}))
    cache = CenterCache(CenterClient(cfg))
    assert cache.get(key) is None
    score = Score(value=0.75, passed=True, reason="4/5", raw={"score": 4, "judge_version": "j1"})
    cache.set(key, score)
    assert json.loads(put.calls[0].request.content)["judge_version"] == "j1"
    assert cache.get(key) == score and get.call_count == 1  # the local layer answers now
    other = "b" * 64
    respx.get(f"{P}/judge-cache/{other}").mock(
        return_value=httpx.Response(200, json={"score": score.model_dump(mode="json")})
    )
    assert cache.get(other) == score
    down = "c" * 64
    respx.get(f"{P}/judge-cache/{down}").mock(side_effect=httpx.ConnectError("down"))
    assert cache.get(down) is None and cache.errors  # a hiccup is a miss, not a failure


@respx.mock
def test_judge_through_the_center_uses_overrides_and_caches_there(cfg):
    respx.get(f"{P}/judge-cache/__").mock(return_value=httpx.Response(404))
    respx.route(method="GET", path__regex=r"/judge-cache/.*").mock(return_value=httpx.Response(404))
    puts = respx.route(method="PUT", path__regex=r"/judge-cache/.*").mock(
        return_value=httpx.Response(201, json={})
    )
    calls = respx.post(f"{P}/model/complete").mock(return_value=_verdict())
    client = CenterClient(cfg)
    ctx = Context(
        providers=CenterProviders(client, default_model="judge/small"),
        cache=CenterCache(client),
        extra={"center_client": client, "judge_models": {"strict": "other/big"}},
    )
    check = judge("strict", "Be strict.")
    score = check.evaluate(Sample(input="q"), Output(value="a"), ctx)
    assert score.passed and score.value == 0.75
    assert json.loads(calls.calls[0].request.content)["model"] == "other/big"  # the override
    assert puts.call_count == 1  # the verdict went to the center
    assert judge("plain", "Be nice.").evaluate(Sample(input="q"), Output(value="a"), ctx).passed
    assert json.loads(calls.calls[1].request.content)["model"] == "judge/small"  # the default
    ctx2 = ctx.model_copy(update={"judge_model": "cli/flag"})
    judge("strict", "Be strict.").evaluate(Sample(input="q"), Output(value="a"), ctx2)
    assert json.loads(calls.calls[2].request.content)["model"] == "cli/flag"  # --judge-model wins


@respx.mock
def test_human_labels_from_the_center(cfg):
    client = CenterClient(cfg)
    ctx = Context(extra={"center_client": client})
    sample, out = Sample(id="s1", input="q"), Output(value="the answer")
    route = respx.get(f"{P}/labels/lookup").mock(return_value=httpx.Response(404))
    check = human(labels="center", check="helpful")
    missing = check.evaluate(sample, out, ctx)
    assert missing.error and "no human label in the center" in missing.error
    assert route.calls[0].request.url.params["output_hash"] == output_hash(out)
    assert route.calls[0].request.url.params["check"] == "helpful"
    respx.get(f"{P}/labels/lookup").mock(
        return_value=httpx.Response(
            200, json={"value": 1.0, "passed": True, "notes": "good", "labeler": "ada", "raw": 5}
        )
    )
    got = check.evaluate(sample, out, ctx)
    assert got.passed and got.reason == "good" and got.raw["labeler"] == "ada"
    unattached = human(labels="center").evaluate(sample, out, Context())
    assert unattached.error and "not attached" in unattached.error


@respx.mock
def test_config_attached_wires_registry_cache_and_human(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALSTONE_API_KEY", "es_test_key")
    respx.get(f"{P}/judge-settings").mock(
        return_value=httpx.Response(
            200,
            json={"project_id": PROJECT, "default_model": "judge/small", "overrides": {"h": "o/b"}},
        )
    )
    (tmp_path / "evalstone.yaml").write_text(
        f"project: demo\ncenter:\n  url: {URL}\n  project: {PROJECT}\n"
        "checks:\n  h:\n    type: human\n  f:\n    type: human\n    labels: my.jsonl\n"
    )
    cfg = Config.load(tmp_path)
    assert cfg.attached
    ctx = cfg.context()
    assert (
        isinstance(ctx.providers, CenterProviders) and ctx.providers.default_model == "judge/small"
    )
    assert isinstance(ctx.cache, CenterCache)
    assert (
        ctx.extra["judge_models"] == {"h": "o/b"}
        and ctx.extra["center_client"] is cfg.center_client()
    )
    assert cfg.check("h").evaluate(Sample(id="s", input="q"), Output(value="a"), Context()).error
    file_mode = cfg.check("f").evaluate(Sample(id="s", input="q"), Output(value="a"), Context())
    assert "my.jsonl" in file_mode.error
    assert Config.model_validate({"project": "x"}).attached is False


@respx.mock
def test_cli_run_pushes_the_report(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from evalstone.cli import app

    monkeypatch.setenv("EVALSTONE_API_KEY", "es_test_key")
    respx.get(f"{P}/judge-settings").mock(
        return_value=httpx.Response(
            200, json={"project_id": PROJECT, "default_model": None, "overrides": {}}
        )
    )
    pushed = respx.post(f"{P}/runs").mock(return_value=httpx.Response(201, json={"id": "run-1"}))
    (tmp_path / "golden.jsonl").write_text('{"input": "hi", "expected": "hi"}\n')
    (tmp_path / "evalstone.yaml").write_text(
        f"project: demo\ncenter:\n  url: {URL}\n  project: {PROJECT}\n"
        "datasets:\n  golden: golden.jsonl\n"
        "checks:\n  same:\n    type: exact\n"
        "suites:\n  ci:\n    dataset: golden\n"
        "    target: {kind: recorded, outputs: {}}\n    checks: [same]\n"
    )
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["run", "ci"])
    assert result.exit_code == 0, result.output
    assert "center → run run-1 stored" in result.output
    body = json.loads(pushed.calls[0].request.content)
    assert body["suite"] == "ci" and body["results"]
    pushed.mock(return_value=httpx.Response(500, json={"detail": "boom"}))
    result = CliRunner().invoke(app, ["run", "ci"])
    assert result.exit_code == 0  # a failed push never fails the run
    assert "run not pushed" in result.output + getattr(result, "stderr", "")


# --- regressions from the #33 review ---------------------------------------------------------


@respx.mock
def test_explicit_labels_center_in_yaml_reaches_the_center(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALSTONE_API_KEY", "es_test_key")
    respx.get(f"{P}/judge-settings").mock(
        return_value=httpx.Response(
            200, json={"project_id": PROJECT, "default_model": None, "overrides": {}}
        )
    )
    lookup = respx.get(f"{P}/labels/lookup").mock(return_value=httpx.Response(404))
    (tmp_path / "evalstone.yaml").write_text(
        f"project: demo\ncenter:\n  url: {URL}\n  project: {PROJECT}\n"
        "checks:\n  h:\n    type: human\n    labels: center\n"
    )
    cfg = Config.load(tmp_path)
    score = cfg.check("h").evaluate(Sample(id="s", input="q"), Output(value="a"), cfg.context())
    assert "in the center" in score.error and lookup.call_count == 1


@respx.mock
def test_mcp_session_honours_the_attach(tmp_path, monkeypatch):
    from evalstone.mcp_server import Session

    monkeypatch.setenv("EVALSTONE_API_KEY", "es_test_key")
    respx.get(f"{P}/judge-settings").mock(
        return_value=httpx.Response(
            200, json={"project_id": PROJECT, "default_model": "j/m", "overrides": {}}
        )
    )
    (tmp_path / "evalstone.yaml").write_text(
        f"project: demo\ncenter:\n  url: {URL}\n  project: {PROJECT}\n"
    )
    session = Session(config_path=str(tmp_path / "evalstone.yaml"))
    cfg = session.config()
    ctx = session.context(cfg)
    assert isinstance(ctx.providers, CenterProviders) and isinstance(ctx.cache, CenterCache)
    assert ctx.extra["center_client"] is cfg.center_client()


def test_cli_center_error_while_building_the_suite_is_a_clean_exit(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from evalstone.cli import app

    monkeypatch.delenv("EVALSTONE_API_KEY", raising=False)
    (tmp_path / "golden.jsonl").write_text('{"input": "hi"}\n')
    (tmp_path / "evalstone.yaml").write_text(
        f"project: demo\ncenter:\n  url: {URL}\n  project: {PROJECT}\n"
        "datasets:\n  golden: golden.jsonl\n"
        "checks:\n  j:\n    type: judge\n    rubric: ok?\n"
        "suites:\n  ci:\n    dataset: golden\n"
        "    target: {kind: prompt, model: openai/x, template: '{input}'}\n    checks: [j]\n"
    )
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["run", "ci"])
    assert result.exit_code == 2 and "EVALSTONE_API_KEY" in result.output + getattr(
        result, "stderr", ""
    )
    assert "Traceback" not in result.output


@respx.mock
def test_cache_treats_a_corrupt_row_and_a_non_object_error_as_misses(cfg):
    key = "d" * 64
    respx.get(f"{P}/judge-cache/{key}").mock(
        return_value=httpx.Response(200, json={"score": {"value": 1.2, "passed": True}})  # invalid
    )
    cache = CenterCache(CenterClient(cfg))
    assert cache.get(key) is None and "ValidationError" in cache.errors[0]
    other = "e" * 64
    respx.get(f"{P}/judge-cache/{other}").mock(
        return_value=httpx.Response(504, json=["upstream timeout"])
    )
    assert cache.get(other) is None and "upstream timeout" in cache.errors[1]


@respx.mock
def test_pairwise_honours_the_center_override(cfg):
    from evalstone.checks.comparison import pairwise

    calls = respx.post(f"{P}/model/complete").mock(
        return_value=_verdict(text='{"winner": "A", "reason": "clearer"}')
    )
    client = CenterClient(cfg)
    ctx = Context(
        providers=CenterProviders(client, default_model="judge/small"),
        extra={"center_client": client, "judge_models": {"better": "other/big"}},
    )
    check = pairwise(
        "better", "Which is clearer?", baseline={"s": "baseline answer"}, model="judge/small"
    )
    check.evaluate(Sample(id="s", input="q"), Output(value="candidate"), ctx)
    assert json.loads(calls.calls[0].request.content)["model"] == "other/big"


@respx.mock
def test_prompt_targets_stay_local_when_attached(tmp_path, monkeypatch):
    from evalstone.providers import Providers

    monkeypatch.setenv("EVALSTONE_API_KEY", "es_test_key")
    respx.get(f"{P}/judge-settings").mock(
        return_value=httpx.Response(
            200, json={"project_id": PROJECT, "default_model": None, "overrides": {}}
        )
    )
    (tmp_path / "evalstone.yaml").write_text(
        f"project: demo\ncenter:\n  url: {URL}\n  project: {PROJECT}\nproviders:\n  openai: {{}}\n"
    )
    cfg = Config.load(tmp_path)
    target = cfg.target({"kind": "prompt", "model": "openai/x", "template": "{input}"})
    assert isinstance(target.providers, Providers)  # the local registry, not the proxy
    assert isinstance(cfg.provider_registry(), CenterProviders)  # judges: the proxy


@respx.mock
def test_cache_lookups_use_the_short_timeout_and_the_cli_warns(cfg):
    key = "f" * 64
    route = respx.get(f"{P}/judge-cache/{key}").mock(side_effect=httpx.ReadTimeout("slow"))
    cache = CenterCache(CenterClient(cfg))
    assert cache.get(key) is None
    assert route.calls[0].request.extensions["timeout"]["read"] == cfg.cache_timeout
    from evalstone.cli import _warn_cache_errors

    _warn_cache_errors(Context(cache=cache))  # prints a warning; must not raise
