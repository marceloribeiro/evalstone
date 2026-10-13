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


def test_override_model_wins_over_every_judge(tmp_path, monkeypatch):
    """`--judge-model` re-routes the judge even when the check names its own model."""
    seen: list[str] = []

    class Recorder:
        name = "fake"

        def complete(self, request):
            seen.append(request.model)
            return ChatResponse(
                text='{"score": 5, "reason": "fine"}',
                model=request.model,
                input_tokens=1,
                output_tokens=1,
            )

    providers = Providers(default_model="anthropic/claude-haiku-5-5")
    providers.register("fake", Recorder())
    providers.override_model = "fake/judge-b"
    assert providers.split("anthropic/claude-haiku-5-5") == ("fake", "judge-b")
    from evalstone.checks.judge import judge

    chk = judge("quality", "Is it good?", model="anthropic/claude-opus-5-5")
    score = chk.evaluate(SAMPLES[0], Output(value="within 30 days"), Context(providers=providers))
    assert score.passed and seen == ["judge-b"]


def test_cli_accepts_judge_model_and_passes_it_to_the_context(tmp_path, monkeypatch):
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
    res = CliRunner().invoke(app, ["run", "nightly", "--judge-model", "openrouter/x/y"])
    assert res.exit_code == 0, res.output
    assert captured["judge_model"] == "openrouter/x/y"
    res = CliRunner().invoke(app, ["gate", "nightly", "--judge-model", "fake/z"])
    assert captured["judge_model"] == "fake/z"


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
