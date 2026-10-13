"""Judge switching and cost honesty: named providers, a run-time judge override, the
short-circuit that spares a judge call on an output a contract check already failed,
and the gate's warning on unpriced calls."""

from __future__ import annotations

from evalstone import Dataset, Gate, Output, RecordedTarget, Sample, Suite
from evalstone.checks._base import FunctionCheck
from evalstone.config import Config
from evalstone.gate import Gate as GateModel
from evalstone.providers import ChatResponse, ProviderError, Providers, price
from evalstone.score import CheckKind, Context, Score

SAMPLES = [
    Sample(id="good", input="q1", expected={"must_include": ["30 days"]}),
    Sample(id="bad", input="q2", expected={"must_include": ["3-5"]}),
]
OUTPUTS = {"good": "within 30 days", "bad": "soon"}


def _judge_like(calls: list[str]) -> FunctionCheck:
    def fn(sample: Sample, output: Output) -> Score:
        calls.append(sample.id)
        return Score.ok("judged")

    return FunctionCheck("verdict", fn, kind=CheckKind.JUDGE)


def _suite(**kw) -> Suite:
    from evalstone.checks.deterministic import contains

    return Suite(
        "s", dataset=Dataset("d", SAMPLES), checks=[contains(), _judge_like(kw.pop("calls"))], **kw
    )


def test_short_circuit_spares_the_judge_on_a_failed_contract():
    calls: list[str] = []
    run = _suite(calls=calls, short_circuit=True).run(RecordedTarget(OUTPUTS))
    assert calls == ["good"]  # the judge never saw the output that failed `contains`
    by = {(r.sample_id, r.check_key): r.score for r in run.results}
    skipped = by[("bad", "verdict")]
    assert skipped.skipped and not skipped.passed and skipped.error is None
    assert skipped.reason == "skipped: contains failed this output"
    assert run.summary.skipped == 1 and run.summary.errors == 0
    # a skip is a failure, not an error: it never trips the error-rate gate on its own
    report = GateModel(max_error_rate=0).evaluate(run)
    assert "FAIL error rate" not in " ".join(report.checks)
    assert run.summary.pass_rate == 0.5


def test_without_short_circuit_every_check_runs():
    calls: list[str] = []
    _suite(calls=calls).run(RecordedTarget(OUTPUTS))
    assert calls == ["good", "bad"]


def test_short_circuit_from_yaml(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from evalstone.cli import app

    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(app, ["init"]).exit_code == 0
    cfg_path = tmp_path / "evalstone.yaml"
    cfg_path.write_text(
        cfg_path.read_text().replace(
            "    gate: {min_pass_rate: 0.9}\n",
            "    gate: {min_pass_rate: 0.9}\n    short_circuit: true\n",
        )
    )
    cfg = Config.load(tmp_path)
    suite, _ = cfg.suite("nightly")
    assert suite.short_circuit is True


def test_named_providers_pick_their_adapter():
    providers = Providers(
        {
            "openrouter": {
                "adapter": "openai",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "k",
            },
            "ollama": {"adapter": "openai", "base_url": "http://localhost:11434/v1"},
            "anthropic": {"api_key": "k"},
        }
    )
    from evalstone.providers.openai_compat import OpenAICompatProvider

    orouter = providers.get("openrouter")
    assert isinstance(orouter, OpenAICompatProvider)
    assert orouter.base_url == "https://openrouter.ai/api/v1"
    assert providers.get("ollama").base_url == "http://localhost:11434/v1"
    assert providers.get("openrouter") is orouter  # one adapter per name
    assert providers.split("openrouter/anthropic/claude-haiku-5-5") == (
        "openrouter",
        "anthropic/claude-haiku-5-5",
    )
    providers.close()


def test_unknown_provider_and_adapter_are_named():
    providers = Providers({"mine": {"adapter": "cohere"}})
    try:
        providers.get("nope")
    except ProviderError as exc:
        assert (
            "unknown provider 'nope'" in str(exc) and "anthropic" in str(exc) and "mine" in str(exc)
        )
    else:  # pragma: no cover
        raise AssertionError("expected ProviderError")
    try:
        providers.get("mine")
    except ProviderError as exc:
        assert "unknown adapter 'cohere'" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ProviderError")


def test_judge_model_override_reroutes_judges_but_never_the_target():
    """`--judge-model` swaps the judge's model, even one named on the check; the prompt
    target (the system under test) keeps its own model, and the override lives on the
    Context, not on the shared registry."""
    seen: list[str] = []

    class Recorder:
        name = "fake"

        def complete(self, request):
            seen.append(request.model)
            text = (
                '{"score": 5, "reason": "fine"}' if "RUBRIC" in (request.system or "") else "answer"
            )
            return ChatResponse(text=text, model=request.model, input_tokens=1, output_tokens=1)

    providers = Providers(default_model="fake/judge-a")
    providers.register("fake", Recorder())
    from evalstone.checks.judge import judge
    from evalstone.target import PromptTarget

    target = PromptTarget(template="{input}", model="fake/under-test", providers=providers)
    chk = judge("quality", "Is it good?", model="fake/judge-a")
    ctx = Context(providers=providers, judge_model="fake/judge-b")
    out = target.produce(SAMPLES[0])
    score = chk.evaluate(SAMPLES[0], out, ctx)
    assert score.passed and seen == ["under-test", "judge-b"]
    assert providers.split("fake/judge-a") == ("fake", "judge-a")  # the registry is untouched
    assert Context(providers=providers).judge_model is None


def test_context_override_does_not_leak_between_calls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from typer.testing import CliRunner

    from evalstone.cli import app

    assert CliRunner().invoke(app, ["init"]).exit_code == 0
    cfg = Config.load(tmp_path)
    assert cfg.context(judge_model="openai/b").judge_model == "openai/b"
    assert cfg.context().judge_model is None


def test_cli_validates_judge_model_before_running(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from evalstone.cli import app

    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(app, ["init"]).exit_code == 0
    captured = {}
    original = Config.context

    def spy(self, *, judge_model=None):
        captured["judge_model"] = judge_model
        return original(self, judge_model=judge_model)

    monkeypatch.setattr(Config, "context", spy)
    res = CliRunner().invoke(app, ["run", "nightly", "--judge-model", "openai/judge-b"])
    assert res.exit_code == 0, res.output
    assert captured["judge_model"] == "openai/judge-b"
    res = CliRunner().invoke(app, ["gate", "nightly", "--judge-model", "openai/judge-c"])
    assert captured["judge_model"] == "openai/judge-c"
    for bad, text in (
        ("claude-haiku-5-5", "<provider>/<model>"),
        ("openrouter/x", "unknown provider"),
    ):
        captured.clear()
        res = CliRunner().invoke(app, ["run", "nightly", "--judge-model", bad])
        assert res.exit_code == 2 and text in res.output, (bad, res.output)
        assert "judge_model" not in captured  # rejected before the run started


def test_gate_warns_when_a_cost_cap_counts_unpriced_calls():
    from evalstone.run import Result, Run, summarise

    def result(unpriced: bool) -> Result:
        return Result(
            sample_id="s",
            check_key="k",
            output=Output(value="x"),
            score=Score.ok("fine", raw={"unpriced": unpriced, "model": "m"}),
        )

    def run(*results: Result) -> Run:
        return Run(
            suite="s",
            dataset="d",
            dataset_hash="0" * 16,
            target={"kind": "recorded"},
            check_keys=["k"],
            started_at=Run.now(),
            finished_at=Run.now(),
            results=list(results),
            summary=summarise(list(results), samples=len(results), checks=1, duration_ms=1.0),
        )

    warned = Gate(max_cost_usd=1.0).evaluate(run(result(True), result(False)))
    assert warned.passed and any(
        line.startswith("WARN 1 result(s) from an unpriced model") for line in warned.checks
    )
    quiet = Gate(max_cost_usd=1.0).evaluate(run(result(False)))
    assert not any(line.startswith("WARN") for line in quiet.checks)
    no_cap = Gate().evaluate(run(result(True)))
    assert not any(line.startswith("WARN") for line in no_cap.checks)


def test_gemini_models_are_priced_from_the_official_table():
    assert price("gemini-2.5-flash", 1_000_000, 1_000_000) == 0.30 + 2.50
    assert price("gemini-3.1-pro-preview", 1_000_000, 0) == 2.00
    assert price("gpt-5", 1_000_000, 0) is None  # not in the table: unpriced, so the gate warns


def test_safety_and_human_checks_are_cheap_and_run_before_judges():
    from evalstone.checks.safety import forbidden

    calls: list[str] = []
    suite = Suite(
        "s", dataset=Dataset("d", SAMPLES), checks=[_judge_like(calls), forbidden(["soon"])]
    )
    assert suite.check_keys == ["forbidden", "verdict"]
    suite.run(RecordedTarget(OUTPUTS))
    assert calls == ["good", "bad"]  # no short_circuit: the judge still ran on both
    suite2 = Suite(
        "s",
        dataset=Dataset("d", SAMPLES),
        checks=[_judge_like(calls := []), forbidden(["soon"])],
        short_circuit=True,
    )
    suite2.run(RecordedTarget(OUTPUTS))
    assert calls == ["good"]  # a safety rule is a contract: its failure spares the judge


def test_per_check_summary_counts_skipped():
    calls: list[str] = []
    run = _suite(calls=calls, short_circuit=True).run(RecordedTarget(OUTPUTS))
    per = {c.key: c for c in run.summary.per_check}
    assert per["verdict"].skipped == 1 and per["contains"].skipped == 0


def test_human_label_failure_does_not_short_circuit_the_judge(tmp_path):
    """A human label is a quality verdict, not a contract: the judge still runs so the
    two can be compared on exactly the samples where they disagree."""
    from evalstone.checks.human import Label, LabelStore, human, output_hash

    store = LabelStore(tmp_path / "labels.jsonl")
    store.add(
        Label(sample_id="good", output_hash=output_hash(OUTPUTS["good"]), value=0.0, passed=False)
    )
    store.add(
        Label(sample_id="bad", output_hash=output_hash(OUTPUTS["bad"]), value=1.0, passed=True)
    )
    calls: list[str] = []
    suite = Suite(
        "s",
        dataset=Dataset("d", SAMPLES),
        checks=[human(labels=tmp_path / "labels.jsonl"), _judge_like(calls)],
        short_circuit=True,
    )
    suite.run(RecordedTarget(OUTPUTS))
    assert calls == ["good", "bad"]  # the human fail on `good` did not skip the judge


def test_unpriced_warning_counts_a_target_call_once_per_sample():
    from evalstone.run import Result, Run, summarise

    def rows(sample: str, n_checks: int, target_unpriced: bool) -> list[Result]:
        out = Output(value="x", metadata={"unpriced": target_unpriced})
        return [
            Result(sample_id=sample, check_key=f"k{i}", output=out, score=Score.ok("fine"))
            for i in range(n_checks)
        ]

    results = rows("a", 4, True) + rows("b", 4, False)
    run = Run(
        suite="s",
        dataset="d",
        dataset_hash="0" * 16,
        target={"kind": "prompt"},
        check_keys=[f"k{i}" for i in range(4)],
        started_at=Run.now(),
        finished_at=Run.now(),
        results=results,
        summary=summarise(results, samples=2, checks=4, duration_ms=1.0),
    )
    report = Gate(max_cost_usd=1.0).evaluate(run)
    assert any(line.startswith("WARN 1 result(s) from an unpriced model") for line in report.checks)


def test_named_entry_never_inherits_the_adapter_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real")
    providers = Providers(
        {"openrouter": {"adapter": "openai", "base_url": "https://openrouter.ai/api/v1"}}
    )
    assert providers.get("openrouter").api_key is None  # a named entry needs its own key
    plain = Providers({"openai": {}})
    assert plain.get("openai").api_key == "sk-real"  # the entry named after the adapter may
