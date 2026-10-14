import textwrap

import pytest

import evalstone as es
from evalstone import Context, Dataset, MemoryCache, Output, PromptTarget, Providers, Sample, Suite
from evalstone.checks.judge import judge, parse_verdict
from evalstone.config import Config
from evalstone.providers import ChatResponse, ProviderError

S = Sample(id="s", input={"question": "Can I return a sale item?"}, expected={"must": ["30 days"]})


class FakeProvider:
    """Replies by looking at the ANSWER text; records every request it saw."""

    name = "openai"

    def __init__(self, reply=None, fail=None, judge_reply=None, stop_reason=None):
        self.reply, self.fail, self.calls = reply, fail, []
        self.judge_reply, self.stop_reason = judge_reply, stop_reason

    def complete(self, request):
        self.calls.append(request)
        if self.fail:
            raise ProviderError(self.fail)
        is_judge = request.system is not None and "RUBRIC" in request.system
        if is_judge and self.judge_reply is not None:
            text = self.judge_reply
        elif is_judge:
            good = "30 days" in request.messages[0].content
            text = (
                '{"score": 5, "reason": "great"}' if good else '{"score": 2, "reason": "missing"}'
            )
        else:
            text = self.reply or ""
        return ChatResponse(
            text=text,
            model=request.model,
            input_tokens=100,
            output_tokens=10,
            cost_usd=0.001,
            latency_ms=12.0,
            stop_reason=self.stop_reason,
        )


def ctx_with(provider, default="openai/judge-model", cache=True):
    reg = Providers(default_model=default)
    reg.register("openai", provider)
    return Context(providers=reg, cache=MemoryCache() if cache else None)


# ── parse ────────────────────────────────────────────────────────────────────


def test_parse_verdict_is_tolerant_but_strict_on_range():
    assert parse_verdict('Sure! {"score": 4, "reason": "fine"} done', 5) == (4, "fine")
    assert parse_verdict('{"score": "3"}', 5) == (3, "")
    assert parse_verdict('{"score": 4.6, "reason": "x"}', 5) == (5, "x")
    with pytest.raises(ValueError, match="no JSON"):
        parse_verdict("I think it is good", 5)
    with pytest.raises(ValueError, match=r"outside 1\.\.5"):
        parse_verdict('{"score": 9}', 5)
    with pytest.raises(ValueError, match="no numeric score"):
        parse_verdict('{"grade": "A"}', 5)


# ── the check ────────────────────────────────────────────────────────────────


def test_judge_scores_passes_and_fails_with_prompt_contract():
    prov = FakeProvider()
    chk = judge("helpful", "Answer must state the return window.")
    ctx = ctx_with(prov)
    good = chk(S, Output(value="Within 30 days with a receipt."), ctx)
    bad = chk(S, Output(value="Ask the store."), ctx)
    assert good.passed and good.value == 1.0 and good.reason == "5/5: great"
    assert not bad.passed and bad.value == 0.25 and bad.reason == "2/5: missing"
    assert good.cost_usd == 0.001 and good.raw["model"] == "judge-model"
    req = prov.calls[0]
    assert req.model == "judge-model" and "Answer must state the return window." in req.system
    assert '"score": <integer 1-5>' in req.system
    assert "REFERENCE" not in req.messages[0].content  # reference excluded by default
    assert "Can I return a sale item?" in req.messages[0].content


def test_judge_threshold_scale_reference_and_version_hash():
    prov = FakeProvider(judge_reply='{"score": 7, "reason": "ok"}')
    chk = judge("graded", "rubric", scale=10, include_reference=True, model="openai/other")
    score = chk(S, Output(value="x"), ctx_with(prov))
    assert score.value == pytest.approx(6 / 9) and score.passed is False  # default threshold 8/10
    sent = prov.calls[0].messages[0].content
    assert "REFERENCE" in sent and "30 days" in sent
    assert prov.calls[0].model == "other"
    loose = judge("graded2", "rubric", scale=10, threshold=0.5)
    seven = ctx_with(FakeProvider(judge_reply='{"score": 7}'))
    assert loose(S, Output(value="x"), seven).passed is True
    assert judge("a", "r").version_hash != judge("a", "r", scale=3).version_hash
    # the key is not part of the judge version
    assert judge("a", "r").version_hash == judge("b", "r").version_hash
    with pytest.raises(ValueError):
        judge("x", "r", scale=1)


def test_judge_errors_are_never_passes():
    chk = judge("h", "r")
    none = chk(S, Output(value="x"), Context(providers=None))
    assert none.error.startswith("judge: no providers")
    down = chk(S, Output(value="x"), ctx_with(FakeProvider(fail="openai: HTTP 500: boom")))
    assert down.passed is False and down.error == "openai: HTTP 500: boom"
    garbage = chk(S, Output(value="x"), ctx_with(FakeProvider(judge_reply="looks fine to me")))
    assert garbage.passed is False and "no JSON" in garbage.error and garbage.cost_usd == 0.001
    no_model = chk(S, Output(value="x"), ctx_with(FakeProvider(), default=None))
    assert no_model.error.startswith("no model given")


# What a real Haiku 5.5 reply looked like when max_tokens=256 cut it mid-reason.
CUT = '{"score": 4, "reason": "The answer directly answers the question with a concrete rule (30 da'


@pytest.mark.parametrize("stop", ["length", "max_tokens", "MAX_TOKENS"])
def test_a_reply_cut_at_the_token_cap_says_so_and_never_passes(stop):
    chk = judge("h", "r", max_tokens=300)
    score = chk(S, Output(value="x"), ctx_with(FakeProvider(judge_reply=CUT, stop_reason=stop)))
    assert score.passed is False and score.cost_usd == 0.001
    assert score.error.startswith(
        "judge: reply truncated at max_tokens=300; raise the check's max_tokens "
        "(no JSON object in judge reply: "
    )
    assert "concrete rule (30 da" in score.error  # the excerpt of what came back survives


def test_truncation_only_explains_a_failed_parse():
    # A complete verdict wins even if the provider then hit the cap.
    full = ctx_with(
        FakeProvider(judge_reply='{"score": 5, "reason": "ok"} and', stop_reason="length")
    )
    assert judge("h", "r")(S, Output(value="x"), full).passed is True
    # A complete but wrong verdict at the cap is the model's answer, not a truncation.
    wrong = ctx_with(
        FakeProvider(judge_reply='{"score": 7, "reason": "x"} and', stop_reason="length")
    )
    assert judge("h", "r")(S, Output(value="x"), wrong).error == "judge: judge score 7 outside 1..5"
    # A normal stop keeps the parse error as it was.
    plain = ctx_with(FakeProvider(judge_reply=CUT, stop_reason="stop"))
    assert "no JSON object" in judge("h", "r")(S, Output(value="x"), plain).error


def test_judge_default_token_budget_fits_a_long_reason():
    prov = FakeProvider()
    judge("h", "r")(S, Output(value="30 days"), ctx_with(prov))
    assert prov.calls[0].max_tokens == 1024


def test_judge_cache_makes_the_second_identical_call_free():
    prov = FakeProvider()
    ctx = ctx_with(prov)
    chk = judge("h", "r")
    first = chk(S, Output(value="Within 30 days."), ctx)
    second = chk(S, Output(value="Within 30 days."), ctx)
    assert len(prov.calls) == 1 and len(ctx.cache) == 1
    assert second.value == first.value and second.cost_usd == 0.0 and second.raw["cached"] is True
    chk(S, Output(value="Different answer."), ctx)
    assert len(prov.calls) == 2
    other_rubric = judge("h2", "another rubric")
    other_rubric(S, Output(value="Within 30 days."), ctx)
    assert len(prov.calls) == 3  # a different judge version is a different cache key
    no_cache = ctx_with(prov, cache=False)
    chk(S, Output(value="Within 30 days."), no_cache)
    chk(S, Output(value="Within 30 days."), no_cache)
    assert len(prov.calls) == 5


# ── suite integration: cheap first, judge costs summed, prompt target ────────


def test_suite_runs_deterministic_checks_before_judges_and_sums_cost():
    prov = FakeProvider()
    ds = Dataset("d", [S])
    suite = Suite("s", dataset=ds, checks=[judge("h", "r"), es.checks.contains(path="must")])
    assert suite.check_keys == ["contains", "h"]
    run = suite.run(lambda inp: "Within 30 days.", ctx=ctx_with(prov))
    assert run.summary.pass_rate == 1.0 and run.summary.cost_usd == pytest.approx(0.001)
    assert run.summary.per_check[1].key == "h" and run.summary.per_check[1].cost_usd == 0.001


def test_prompt_target_formats_template_and_reports_cost():
    prov = FakeProvider(reply="Within 30 days.")
    reg = Providers(default_model="openai/gen")
    reg.register("openai", prov)
    t = PromptTarget("openai/gen", "Q: {question}\nA:", system="You are support.", providers=reg)
    out = t.produce(S)
    assert out.value == "Within 30 days." and out.cost_usd == 0.001 and out.model == "gen"
    assert prov.calls[0].messages[0].content == "Q: Can I return a sale item?\nA:"
    assert prov.calls[0].system == "You are support."
    desc = t.describe()
    assert desc["kind"] == "prompt" and desc["model"] == "openai/gen" and desc["system"] is True
    other = PromptTarget("openai/gen", "Reworded: {question}", system="You are support.")
    assert other.describe()["prompt_hash"] != desc["prompt_hash"]
    missing = PromptTarget("openai/gen", "{missing}", providers=reg).produce(S)
    assert missing.error.startswith("prompt target: template placeholder")
    assert PromptTarget("openai/gen").produce(S).error == "prompt target: no providers configured"
    via_factory = es.target("prompt", model="openai/gen", providers=reg)
    assert via_factory.produce(S).value == "Within 30 days."


def test_config_wires_providers_judges_prompt_targets_and_prices(tmp_path, monkeypatch):
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "golden.jsonl").write_text(
        '{"id": "a", "input": {"question": "q"}, "expected": {"must": ["30 days"]}}\n'
    )
    (tmp_path / "evalstone.yaml").write_text(
        textwrap.dedent(
            """
            project: demo
            datasets: { golden: evals/golden.jsonl }
            providers:
              openai: { base_url: http://localhost:11434/v1, api_key_env: MY_LLM_KEY }
            judges: { default_model: openai/judge }
            prices: { judge: [1.0, 2.0] }
            checks:
              helpful: { type: judge, rubric: "Be helpful.", scale: 3 }
              must: { type: contains, path: must }
            suites:
              s:
                dataset: golden
                target: { kind: prompt, model: openai/gen, template: "Answer: {question}" }
                checks: [helpful, must]
            """
        )
    )
    monkeypatch.setenv("MY_LLM_KEY", "k")
    cfg = Config.load(tmp_path)
    assert cfg.provider_registry().get("openai").base_url == "http://localhost:11434/v1"
    assert cfg.provider_registry().get("openai").api_key == "k"
    assert cfg.prices == {"judge": (1.0, 2.0)}
    prov = FakeProvider(reply="Within 30 days.", judge_reply='{"score": 3, "reason": "ok"}')
    cfg.provider_registry().register("openai", prov)
    suite, target = cfg.suite("s")
    assert target.describe()["kind"] == "prompt" and target.model == "openai/gen"
    cfg.suites["s"].target = {"kind": "prompt", "template": "x"}
    with pytest.raises(ValueError, match="needs its own `model`"):
        cfg.suite("s")
    run = suite.run(target, ctx=cfg.context())
    assert run.summary.pass_rate == 1.0 and run.summary.results == 2
    cfg.checks["bad"] = {"type": "judge"}
    with pytest.raises(ValueError, match=r"check 'bad' \(judge\): .*rubric"):
        cfg.check("bad")


# ── review findings on PR 5 ──────────────────────────────────────────────────


def test_binary_scale_can_fail_and_pass_level_is_a_rubric_level():
    yes_no = judge("ok", "r", scale=2)
    no = ctx_with(FakeProvider(judge_reply='{"score": 1}'))
    yes = ctx_with(FakeProvider(judge_reply='{"score": 2}'))
    assert yes_no(S, Output(value="x"), no).passed is False
    assert yes_no(S, Output(value="x"), yes).passed is True
    at3 = judge("g", "r", scale=5, pass_level=3)
    three = ctx_with(FakeProvider(judge_reply='{"score": 3}'))
    assert at3(S, Output(value="x"), three).passed is True and at3.pass_at == 0.5
    with pytest.raises(ValueError, match=r"0\.\.1 fraction"):
        judge("bad", "r", scale=5, threshold=4)
    with pytest.raises(ValueError, match="not both"):
        judge("bad", "r", pass_level=4, threshold=0.5)
    with pytest.raises(ValueError, match="pass_level must be within"):
        judge("bad", "r", scale=5, pass_level=9)


def test_cache_serves_the_raw_verdict_so_thresholds_differ_per_judge():
    prov = FakeProvider(judge_reply='{"score": 3, "reason": "meh"}')
    ctx = ctx_with(prov)
    strict = judge("a", "r")  # passes at level 4
    loose = judge("b", "r", threshold=0.5)
    first = strict(S, Output(value="x"), ctx)
    second = loose(S, Output(value="x"), ctx)
    assert len(prov.calls) == 1  # same rubric, same model, same prompt → one model call
    assert first.passed is False and second.passed is True
    assert second.raw["cached"] is True and second.reason == "3/5: meh"


def test_judge_version_includes_the_resolved_default_model():
    prov = FakeProvider()
    chk = judge("h", "r")  # no model: relies on judges.default_model
    a = chk(S, Output(value="Within 30 days."), ctx_with(prov, default="openai/judge-a"))
    b = chk(S, Output(value="Within 30 days."), ctx_with(prov, default="openai/judge-b"))
    assert a.raw["judge_version"] != b.raw["judge_version"]
    assert len(prov.calls) == 2  # different resolved model → different cache key


def test_verdict_records_the_routed_model_fresh_and_cached():
    """`judge_model` is what Promote pins: `<provider>/<model>` as routed, not `resp.model`."""
    from evalstone.score import Score

    chk = judge("h", "r")
    ctx = ctx_with(FakeProvider())
    fresh = chk(S, Output(value="30 days"), ctx)
    assert fresh.raw["judge_model"] == "openai/judge-model"
    assert chk(S, Output(value="30 days"), ctx).raw["judge_model"] == "openai/judge-model"
    # a cache entry written by an older library (no judge_model) still gets it on the way out
    key, old = next(iter(ctx.cache._data.items()))
    ctx.cache._data[key] = Score.model_validate(
        {**old.model_dump(), "raw": {k: v for k, v in old.raw.items() if k != "judge_model"}}
    )
    assert chk(S, Output(value="30 days"), ctx).raw["judge_model"] == "openai/judge-model"
