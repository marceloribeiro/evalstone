import pytest

from evalstone import Check, CheckKind, Context, Output, Sample, Score, check, registry


def test_error_is_never_a_pass():
    assert Score(value=1.0, passed=True, error="boom").passed is False
    assert Score.errored("timeout").passed is False
    assert Score.errored("timeout").error == "timeout"


def test_value_is_bounded():
    with pytest.raises(ValueError):
        Score(value=1.5, passed=True)
    with pytest.raises(ValueError):
        Score(value=-0.1, passed=False)


def test_from_value_uses_threshold():
    assert Score.from_value(0.8, threshold=0.7).passed is True
    assert Score.from_value(0.6, threshold=0.7).passed is False


def test_output_text_view():
    assert Output(value="plain").text == "plain"
    assert Output(value={"b": 1, "a": 2}).text == '{"a": 2, "b": 1}'
    assert Output(value=None).text == ""
    assert Output.failed("timeout").error == "timeout"


def test_decorated_function_returning_bool_is_a_registered_check():
    @check("no_apology")
    def no_apology(sample, output):
        """Fails when the answer apologises."""
        return "sorry" not in output.text.lower()

    assert isinstance(no_apology, Check)
    assert no_apology.kind == CheckKind.DETERMINISTIC
    assert no_apology.description == "Fails when the answer apologises."
    assert registry.get("no_apology") is no_apology
    assert "no_apology" in registry
    assert registry.keys() == ["no_apology"]

    sample = Sample(input="q")
    assert no_apology(sample, Output(value="Here you go")).passed is True
    assert no_apology(sample, Output(value="Sorry, no")).passed is False


def test_decorated_function_may_return_float_or_score_and_receive_ctx():
    @check("graded", kind="judge", version=3)
    def graded(sample, output, ctx):
        return Score.from_value(ctx.extra["v"], threshold=0.5, reason="ctx-driven")

    @check("ratio")
    def ratio(sample, output):
        return 0.25

    score = graded(Sample(input=1), Output(value=""), Context(extra={"v": 0.9}))
    assert score.passed and score.reason == "ctx-driven"
    assert graded.kind == CheckKind.JUDGE and graded.version == 3
    r = ratio(Sample(input=1), Output(value=""))
    assert r.value == 0.25 and r.passed is False
    assert r.latency_ms > 0


def test_crashing_check_becomes_an_errored_score_not_an_exception():
    @check("boom")
    def boom(sample, output):
        raise RuntimeError("judge down")

    score = boom(Sample(input=1), Output(value=""))
    assert score.passed is False
    assert score.error == "RuntimeError: judge down"


def test_bad_return_type_is_an_error_score():
    @check("weird")
    def weird(sample, output):
        return "yes"

    score = weird(Sample(input=1), Output(value=""))
    assert score.error is not None and "TypeError" in score.error


def test_registry_refuses_duplicates_unless_replace():
    @check("k")
    def one(sample, output):
        return True

    with pytest.raises(ValueError, match="already registered"):

        @check("k")
        def two(sample, output):
            return False

    @check("k", register=False)
    def three(sample, output):
        return False

    registry.register(three, replace=True)
    assert registry.get("k") is three
    with pytest.raises(KeyError, match="unknown check"):
        registry.get("nope")


# ── review findings on PR 1 ──────────────────────────────────────────────────


def test_factories_accept_overrides_without_keyword_collisions():
    s = Score.errored("timeout", reason="judge unreachable after 3 retries")
    assert s.error == "timeout" and s.reason == "judge unreachable after 3 retries" and not s.passed
    assert Score.ok("fine", value=0.9).value == 0.9
    assert Score.fail("meh", value=0.3).value == 0.3
    assert Output.failed("boom", value={"partial": True}).value == {"partial": True}


def test_output_text_handles_models_and_dataclasses():
    from dataclasses import dataclass

    from pydantic import BaseModel

    class Resp(BaseModel):
        answer: str

    @dataclass
    class Row:
        n: int

    assert Output(value=Resp(answer="hi")).text == '{"answer": "hi"}'
    assert Output(value=Row(n=1)).text == '{"n": 1}'
    assert Output(value={"s": {2, 1}}).text == '{"s": [1, 2]}'


def test_registry_replaces_only_a_reimported_function_not_a_closure_twin():
    def make(v):
        @check("dyn")
        def inner(sample, output):
            return v

        return inner

    make(True)
    with pytest.raises(ValueError, match="already registered"):
        make(False)
    # a re-import executes the same source in a fresh module: new globals, same qualname
    ns1, ns2 = {"check": check}, {"check": check}
    src = "@check('reimp')\ndef f(sample, output):\n    return True\n"
    exec(compile(src, "<mod>", "exec"), ns1)
    exec(compile(src, "<mod>", "exec"), ns2)
    assert registry.get("reimp") is ns2["f"]
