import textwrap

import pytest

from evalstone import Context, MemoryCache, Output, Providers, RecordedTarget, Sample
from evalstone.checks import comparison, rag
from evalstone.checks.comparison import pairwise, parse_winner
from evalstone.config import Config
from evalstone.providers import ChatResponse, ProviderError

S = Sample(
    id="s",
    input={
        "question": "Can I return a sale item?",
        "context": "Sale items: 30 days, store credit.",
    },
)


class JudgeFake:
    """Scores 5 when the answer mentions the context; for pairwise prefers the longer answer."""

    name = "openai"

    def __init__(self, winner=None, fail=None):
        self.calls, self.winner, self.fail = [], winner, fail

    def complete(self, request):
        self.calls.append(request)
        if self.fail:
            raise ProviderError(self.fail)
        user = request.messages[0].content
        if "ANSWER A:" in user:
            if self.winner:
                text = self.winner
            else:
                a = user.split("ANSWER A:")[1].split("ANSWER B:")[0].strip()
                b = user.split("ANSWER B:")[1].strip()
                text = '{"winner": "%s", "reason": "longer"}' % ("A" if len(a) >= len(b) else "B")
        else:
            good = "store credit" in user.split("ANSWER:")[1]
            text = (
                '{"score": 5, "reason": "supported"}'
                if good
                else '{"score": 1, "reason": "unsupported"}'
            )
        return ChatResponse(text=text, model=request.model, cost_usd=0.002, latency_ms=5.0)


def ctx(fake):
    reg = Providers(default_model="openai/judge")
    reg.register("openai", fake)
    return Context(providers=reg, cache=MemoryCache())


def test_rag_checks_are_judges_with_field_aware_rubrics():
    fake = JudgeFake()
    c = ctx(fake)
    assert rag.faithfulness()(S, Output(value="30 days, store credit only."), c).passed
    assert rag.faithfulness()(S, Output(value="Full refund any time."), c).passed is False
    assert "`context`" in fake.calls[0].system and fake.calls[0].model == "judge"
    custom = rag.context_relevance(question="q", context="docs")
    assert "`q`" in custom.rubric and "`docs`" in custom.rubric
    assert rag.answer_relevance(model="openai/other").model == "openai/other"
    assert {rag.faithfulness().key, rag.context_relevance().key, rag.answer_relevance().key} == {
        "faithfulness",
        "context_relevance",
        "answer_relevance",
    }
    assert rag.faithfulness().kind == "judge"


def test_parse_winner():
    assert parse_winner('{"winner": "b", "reason": "x"}') == ("B", "x")
    assert parse_winner('ok {"winner": "tie"}') == ("TIE", "")
    with pytest.raises(ValueError, match="must be A, B or tie"):
        parse_winner('{"winner": "C"}')
    with pytest.raises(ValueError, match="no JSON"):
        parse_winner("A is better")


def test_pairwise_judges_both_orders_and_combines():
    fake = JudgeFake()
    chk = pairwise("better", "Prefer the more complete answer.", baseline={"s": "30 days."})
    c = ctx(fake)
    win = chk(S, Output(value="30 days, store credit only, with a receipt."), c)
    assert win.value == 1.0 and win.passed and win.reason.startswith("candidate wins")
    assert len(fake.calls) == 2 and win.cost_usd == pytest.approx(0.004)
    assert "ANSWER A:\n30 days, store credit only" in fake.calls[0].messages[0].content
    assert "ANSWER A:\n30 days." in fake.calls[1].messages[0].content
    lose = chk(S, Output(value="No."), c)
    assert lose.value == 0.0 and lose.passed is False and lose.reason.startswith("candidate loses")
    assert chk.kind == "comparison"


def test_pairwise_ties_single_order_cache_and_errors():
    tie = JudgeFake(winner='{"winner": "tie", "reason": "same"}')
    chk = pairwise("better", "r", baseline={"s": "x"})
    c = ctx(tie)
    score = chk(S, Output(value="y"), c)
    assert score.value == 0.5 and score.passed and "ties/split" in score.reason
    chk(S, Output(value="y"), c)
    assert len(tie.calls) == 2  # cached: no new calls
    assert chk(S, Output(value="y"), c).cost_usd == 0.0

    one = JudgeFake()
    single = pairwise("b1", "r", baseline=RecordedTarget({"s": "x"}), both_orders=False)
    assert single(S, Output(value="much longer answer"), ctx(one)).value == 1.0
    assert len(one.calls) == 1

    missing = chk(Sample(id="other", input="q"), Output(value="y"), c)
    assert missing.error.startswith("pairwise: baseline: no recorded output")
    down = chk(S, Output(value="z"), ctx(JudgeFake(fail="openai: HTTP 500")))
    assert down.passed is False and down.error == "openai: HTTP 500"
    garbage = chk(S, Output(value="w"), ctx(JudgeFake(winner="dunno")))
    assert garbage.error.startswith("pairwise: no JSON")
    none = chk(S, Output(value="v"), Context(providers=None))
    assert none.error == "pairwise: no providers configured"


def test_config_resolves_dotted_check_types(tmp_path):
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "golden.jsonl").write_text(
        '{"id": "s", "input": {"question": "q", "context": "c"}}\n'
    )
    (tmp_path / "evals" / "base.jsonl").write_text('{"id": "s", "output": "base answer"}\n')
    (tmp_path / "evalstone.yaml").write_text(
        textwrap.dedent(
            """
            project: demo
            datasets: { golden: evals/golden.jsonl }
            judges: { default_model: openai/judge }
            checks:
              faithful: { type: rag.faithfulness }
              relevant: { type: rag.answer_relevance, question: question }
              refuse: { type: safety.refusal }
              clean: { type: safety.no_pii, kinds: [email] }
              banned: { type: safety.forbidden, phrases: [guaranteed] }
              looked_up: { type: trajectory.tool_called, name: lookup, min_times: 1 }
              ordered: { type: trajectory.tool_order, before: lookup, after: refund }
              bounded: { type: trajectory.max_steps, n: 8 }
              better:
                type: comparison.pairwise
                rubric: "Prefer complete."
                baseline: { kind: recorded, path: evals/base.jsonl }
            suites:
              s:
                dataset: golden
                target: { kind: recorded, outputs: { s: "an answer" } }
                checks:
                  [faithful, relevant, refuse, clean, banned, looked_up, ordered, bounded, better]
            """
        )
    )
    cfg = Config.load(tmp_path)
    suite, _ = cfg.suite("s")
    kinds = {c.key: str(c.kind) for c in suite.checks}
    assert kinds == {
        "faithful": "judge",
        "relevant": "judge",
        "refuse": "safety",
        "clean": "safety",
        "banned": "safety",
        "looked_up": "trajectory",
        "ordered": "trajectory",
        "bounded": "trajectory",
        "better": "comparison",
    }
    # cheap kinds first: trajectory, then safety/judge/comparison in declared order
    assert suite.check_keys[:3] == ["looked_up", "ordered", "bounded"]
    assert comparison.pairwise is pairwise


# ── review findings on PR 6 ──────────────────────────────────────────────────


def test_pairwise_labels_every_mixed_outcome_consistently():
    replies = iter(['{"winner": "A", "reason": "x"}', '{"winner": "tie", "reason": "y"}'])

    class Mixed(JudgeFake):
        def complete(self, request):
            self.calls.append(request)
            return ChatResponse(text=next(replies), model=request.model, cost_usd=0.001)

    chk = pairwise("b", "r", baseline={"s": "x"})
    score = chk(S, Output(value="y"), ctx(Mixed()))
    assert score.value == 0.75 and score.passed and score.reason.startswith("candidate mostly wins")


def test_pairwise_identity_tracks_the_resolved_model_and_both_orders():
    prov = JudgeFake(winner='{"winner": "tie"}')
    chk = pairwise("b", "r", baseline={"s": "x"})
    a = chk(S, Output(value="y"), ctx(prov))
    reg_b = Providers(default_model="openai/other")
    reg_b.register("openai", prov)
    b = chk(S, Output(value="y"), Context(providers=reg_b, cache=MemoryCache()))
    assert a.raw["judge_version"] != b.raw["judge_version"]
    single = pairwise("b", "r", baseline={"s": "x"}, both_orders=False)
    c = single(S, Output(value="y"), ctx(prov))
    assert c.raw["judge_version"] != a.raw["judge_version"]


def test_pairwise_cache_hit_keeps_the_baseline_cost():
    prov = JudgeFake(winner='{"winner": "tie"}')
    costly = RecordedTarget({"s": {"value": "x", "cost_usd": 0.25}})
    chk = pairwise("b", "r", baseline=costly)
    c = ctx(prov)
    first = chk(S, Output(value="y"), c)
    second = chk(S, Output(value="y"), c)
    assert first.cost_usd == pytest.approx(0.25 + 0.004)
    assert second.cost_usd == pytest.approx(0.25) and second.raw["cached"] is True


def test_config_baseline_mapping_form_and_target_form(tmp_path):
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "golden.jsonl").write_text('{"id": "s", "input": "q"}\n')
    (tmp_path / "evalstone.yaml").write_text(
        textwrap.dedent(
            """
            project: demo
            datasets: { golden: evals/golden.jsonl }
            judges: { default_model: openai/judge }
            checks:
              mapped: { type: comparison.pairwise, rubric: r, baseline: { s: "base answer" } }
              targeted:
                type: comparison.pairwise
                rubric: r
                baseline: { kind: recorded, outputs: { s: "base answer" } }
            suites:
              s:
                dataset: golden
                target: { kind: recorded, outputs: { s: "cand" } }
                checks: [mapped, targeted]
            """
        )
    )
    cfg = Config.load(tmp_path)
    suite, target = cfg.suite("s")
    assert suite.check_keys == ["mapped", "targeted"]
    c = cfg.context()
    c.providers.register("openai", JudgeFake(winner='{"winner": "A"}'))
    run = suite.run(target, ctx=c)
    assert run.summary.errors == 0 and run.summary.results == 2
