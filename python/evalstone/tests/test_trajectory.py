from evalstone import Dataset, Output, Sample, Suite
from evalstone.checks import trajectory as tj

S = Sample(id="s", input="refund order 42")
GOOD = Output(
    value={
        "answer": "Refunded.",
        "steps": [
            {"tool": "lookup_order", "args": {"id": 42}},
            {"tool": "issue_refund", "args": {"id": 42, "amount": 10}},
        ],
    }
)
LOOPY = Output(
    value={"answer": "", "steps": [{"tool": "lookup_order", "args": {"id": 42}}] * 4},
    metadata={},
)


def test_steps_of_reads_value_or_metadata():
    assert len(tj.steps_of(GOOD)) == 2
    assert tj.steps_of(Output(value="plain")) is None
    assert tj.steps_of(Output(value={"steps": []})) == []
    assert len(tj.steps_of(Output(value="x", metadata={"steps": [{"tool": "a"}]}))) == 1
    assert tj.steps_of(Output(value={"trace": [{"tool": "a"}]}), key="trace")[0]["tool"] == "a"


def test_tool_called_counts_and_args_predicate():
    assert tj.tool_called("lookup_order")(S, GOOD).reason == "lookup_order called 1x"
    capped = tj.tool_called("issue_refund", max_times=0)(S, GOOD)
    assert capped.reason == "issue_refund called 1x, expected ≤ 0"
    assert tj.tool_called("ship")(S, GOOD).reason == "ship called 0x, expected ≥ 1"
    big = tj.tool_called("issue_refund", args=lambda a: a.get("amount", 0) > 100)
    assert big(S, GOOD).passed is False
    assert tj.tool_called("x").key == "called_x" and tj.tool_called("x").kind == "trajectory"


def test_tool_order_max_steps_repeats_and_finished():
    assert tj.tool_order("lookup_order", "issue_refund")(S, GOOD).passed
    reversed_out = Output(value={"steps": list(reversed(GOOD.value["steps"]))})
    assert tj.tool_order("lookup_order", "issue_refund")(S, reversed_out).reason == (
        "issue_refund at step 0 before any lookup_order"
    )
    assert tj.max_steps(2)(S, GOOD).passed and tj.max_steps(3)(S, LOOPY).reason == "4 steps > max 3"
    assert tj.no_repeated_calls()(S, GOOD).passed
    assert tj.no_repeated_calls()(S, LOOPY).reason.startswith("repeated call x4: lookup_order")
    assert tj.no_repeated_calls(max_repeats=4)(S, LOOPY).passed
    assert tj.finished()(S, GOOD).passed and tj.finished()(S, LOOPY).reason == "no final answer"
    assert tj.finished()(S, Output(value="text")).passed is False


def test_trajectory_checks_are_cheap_and_run_first_in_a_suite():
    suite = Suite(
        "agent",
        dataset=Dataset("d", [S]),
        checks=[tj.max_steps(5), tj.finished(), tj.no_repeated_calls()],
    )
    run = suite.run(lambda inp: GOOD.value)
    assert run.summary.pass_rate == 1.0 and run.summary.cost_usd == 0.0


# ── review findings on PR 6 ──────────────────────────────────────────────────


def test_missing_trajectory_is_an_error_never_a_vacuous_pass():
    checks = (tj.max_steps(3), tj.tool_order("a", "b"), tj.no_repeated_calls(), tj.tool_called("a"))
    for chk in checks:
        for out in (Output(value="plain text"), Output(value={"trace": [{"tool": "a"}]})):
            score = chk(S, out)
            assert score.passed is False and score.error.startswith("no trajectory recorded")
    empty = Output(value={"steps": []})
    assert tj.max_steps(3)(S, empty).passed and tj.no_repeated_calls()(S, empty).passed
    assert tj.steps_of(Output(value={"trace": [{"tool": "a"}]}), key="trace") is not None


def test_non_dict_args_are_tolerated():
    steps = [{"tool": "search", "args": "q=x"}, {"tool": "search", "args": "q=x"}]
    raw = Output(value={"steps": steps})
    assert tj.no_repeated_calls()(S, raw).reason.startswith("repeated call x2: search")
    seen = []
    tj.tool_called("search", args=lambda a: seen.append(a) or True)(S, raw)
    assert seen[0] == {"value": "q=x"}
    none = Output(value={"steps": [{"tool": "search"}]})
    assert tj.no_repeated_calls()(S, none).passed
