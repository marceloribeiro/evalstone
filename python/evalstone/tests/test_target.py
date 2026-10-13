import json

import httpx
import pytest
import respx

from evalstone import CallableTarget, HttpTarget, Output, RecordedTarget, Sample, Target, target

S = Sample(id="s1", input={"q": "hello"})


def test_callable_target_wraps_values_and_measures_latency():
    t = CallableTarget(lambda inp: inp["q"].upper())
    out = t.produce(S)
    assert isinstance(t, Target)
    assert out.value == "HELLO" and out.latency_ms > 0 and out.error is None
    assert t.describe()["kind"] == "callable"


def test_callable_target_passes_through_outputs_and_catches_exceptions():
    t = CallableTarget(lambda inp: Output(value="x", cost_usd=0.01, model="m"))
    out = t.produce(S)
    assert out.cost_usd == 0.01 and out.model == "m" and out.latency_ms > 0

    def boom(_):
        raise RuntimeError("down")

    failed = CallableTarget(boom).produce(S)
    assert failed.error == "RuntimeError: down" and failed.value is None


def test_callable_target_can_receive_the_whole_sample():
    t = CallableTarget(lambda s: s.id, whole_sample=True)
    assert t.produce(S).value == "s1"


@respx.mock
def test_http_target_posts_input_and_digs_response_path():
    route = respx.post("http://api.test/answer").mock(
        return_value=httpx.Response(200, json={"data": {"answer": "hi"}, "usage": 1})
    )
    t = HttpTarget("http://api.test/answer", response_path="data.answer", headers={"X-K": "1"})
    out = t.produce(S)
    assert out.value == "hi" and out.error is None
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"input": {"q": "hello"}}
    assert route.calls.last.request.headers["X-K"] == "1"


@respx.mock
def test_http_target_body_template_and_http_errors():
    route = respx.post("http://api.test/chat").mock(return_value=httpx.Response(500, text="nope"))
    body = {"messages": [{"role": "user", "content": "{input}"}]}
    t = HttpTarget("http://api.test/chat", body=body)
    out = t.produce(Sample(id="x", input="hello there"))
    assert out.error is not None and "500" in out.error
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"messages": [{"role": "user", "content": "hello there"}]}


def test_recorded_target_from_dict_and_jsonl(tmp_path):
    t = RecordedTarget({"s1": "recorded answer"})
    assert t.produce(S).value == "recorded answer"
    assert t.produce(Sample(id="other", input=1)).error == "no recorded output for sample other"

    path = tmp_path / "outputs.jsonl"
    path.write_text(
        json.dumps({"id": "s1", "output": {"value": "rich", "cost_usd": 0.5, "model": "gpt"}})
        + "\n",
        encoding="utf-8",
    )
    rich = RecordedTarget(path).produce(S)
    assert rich.value == "rich" and rich.cost_usd == 0.5 and rich.model == "gpt"
    desc = RecordedTarget(path).describe()
    assert desc == {"kind": "recorded", "name": "outputs.jsonl", "count": 1}


def test_target_factory():
    assert isinstance(target("callable", fn=len), CallableTarget)
    assert isinstance(target("http", url="http://x"), HttpTarget)
    assert isinstance(target("recorded", outputs={}), RecordedTarget)
    try:
        target("magic")
    except ValueError as exc:
        assert "unknown target kind" in str(exc)


# ── review findings on PR 3 ──────────────────────────────────────────────────


@respx.mock
def test_http_body_placeholders_are_filled_on_string_leaves():
    route = respx.post("http://api.test/chat").mock(
        return_value=httpx.Response(200, json={"ok": 1})
    )
    body = {"messages": [{"role": "user", "content": "Answer briefly: {input}"}], "raw": "{input}"}
    HttpTarget("http://api.test/chat", body=body).produce(Sample(id="x", input={"q": "hi"}))
    sent = json.loads(route.calls.last.request.content)
    assert sent["messages"][0]["content"] == 'Answer briefly: {"q": "hi"}'
    assert sent["raw"] == {"q": "hi"}
    HttpTarget("http://api.test/chat", body=body).produce(Sample(id="y", input="plain {input}"))
    assert json.loads(route.calls.last.request.content)["raw"] == "plain {input}"


@respx.mock
def test_http_response_path_indexes_lists_and_get_sends_json():
    respx.post("http://api.test/v1").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})
    )
    t = HttpTarget("http://api.test/v1", response_path="choices.0.message.content")
    assert t.produce(S).value == "hi"
    get = respx.get("http://api.test/q").mock(return_value=httpx.Response(200, json="ok"))
    HttpTarget("http://api.test/q", method="GET").produce(Sample(id="g", input={"q": "hello"}))
    assert get.calls.last.request.url.params["input"] == '{"q": "hello"}'


@respx.mock
def test_http_target_keeps_one_client_and_closes_it():
    respx.post("http://api.test/x").mock(return_value=httpx.Response(200, json=1))
    with HttpTarget("http://api.test/x", name="my-api") as t:
        t.produce(S)
        first = t.client
        t.produce(S)
        assert t.client is first and t.describe()["name"] == "my-api"
    assert t._client is None


def test_target_factory_forwards_config_and_validates():
    assert target("recorded", outputs={}, name="v2").name == "v2"
    assert target("callable", fn=len, name="n").name == "n"
    with pytest.raises(ValueError, match="needs `outputs` or `path`"):
        target("recorded")
    with pytest.raises(ValueError, match="callable target"):
        target("callable", nope=1)
