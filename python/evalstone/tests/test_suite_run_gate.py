import json

import pytest

import evalstone as es
from evalstone import Dataset, Gate, GateFailed, Output, RecordedTarget, Run, Suite, check, compare

DS = Dataset.from_records(
    "golden",
    [
        {"id": "a", "input": "q1", "expected": {"must_include": ["30 days"]}, "tags": ["refund"]},
        {
            "id": "b",
            "input": "q2",
            "expected": {"must_include": ["receipt"]},
            "tags": ["refund", "edge"],
        },
        {"id": "c", "input": "q3", "expected": {"must_include": ["free"]}, "tags": ["shipping"]},
    ],
)
GOOD = {"a": "Within 30 days.", "b": "Bring the receipt.", "c": "Shipping is free."}


def make_suite(gate=None):
    checks = [es.checks.contains(), es.checks.length(max_words=10)]
    return Suite("support", dataset=DS, checks=checks, gate=gate)


def test_run_scores_every_sample_with_every_check_and_summarises():
    run = make_suite().run(RecordedTarget(GOOD))
    s = run.summary
    assert s.samples == 3 and s.checks == 2 and s.results == 6
    assert s.pass_rate == 1.0 and s.errors == 0 and s.mean_score == 1.0
    assert [c.key for c in s.per_check] == ["contains", "length"]
    assert s.per_tag == {"edge": 1.0, "refund": 1.0, "shipping": 1.0}
    assert run.dataset_hash == DS.content_hash and run.check_keys == ["contains", "length"]
    assert run.target == {"kind": "recorded", "name": "recorded", "count": 3}
    assert run.gate_passed is None
    assert "total" in run.table() and "support" in run.table()


def test_failures_and_per_tag_breakdown():
    run = make_suite().run(RecordedTarget({**GOOD, "b": "No idea."}))
    assert run.summary.pass_rate == pytest.approx(5 / 6)
    assert [f.sample_id for f in run.failures()] == ["b"]
    assert run.summary.per_tag["edge"] == 0.5 and run.summary.per_tag["shipping"] == 1.0


def test_target_failure_is_an_error_for_every_check_never_a_pass():
    run = make_suite().run(RecordedTarget({"a": GOOD["a"]}))  # b and c unrecorded
    assert run.summary.errors == 4 and run.summary.error_rate == pytest.approx(4 / 6)
    assert all(r.score.error.startswith("target:") for r in run.results if r.score.error)


def test_cheap_checks_run_first_and_string_keys_resolve_from_registry():
    @check("judgey", kind="judge")
    def judgey(sample, output):
        return True

    suite = Suite("s", dataset=DS, checks=["judgey", es.checks.length()])
    assert suite.check_keys == ["length", "judgey"]
    with pytest.raises(ValueError, match="duplicate check keys"):
        Suite("s", dataset=DS, checks=[es.checks.length(), es.checks.length()])
    with pytest.raises(ValueError, match="at least one check"):
        Suite("s", dataset=DS, checks=[])


def test_plain_callable_is_a_target_and_on_sample_progress_fires():
    seen = []
    ids = {"q1": "a", "q2": "b", "q3": "c"}
    run = make_suite().run(lambda q: GOOD[ids[q]], on_sample=lambda i, n: seen.append((i, n)))
    assert run.summary.pass_rate == 1.0 and seen == [(1, 3), (2, 3), (3, 3)]
    assert run.target["kind"] == "callable"


def test_gate_thresholds_and_error_tolerance():
    gate = Gate(min_pass_rate=0.9, max_cost_usd=1.0)
    suite = make_suite(gate)
    run = suite.run(RecordedTarget({**GOOD, "b": "No idea."}))
    assert run.gate_passed is False
    assert any(line.startswith("FAIL pass rate 83.3%") for line in run.gate_lines)
    with pytest.raises(GateFailed) as exc:
        suite.enforce(run)
    assert "pass rate" in str(exc.value)

    partial = make_suite(Gate()).run(RecordedTarget({"a": GOOD["a"]}))
    assert partial.gate_passed is False  # default max_error_rate = 0
    tolerant = make_suite(Gate(max_error_rate=0.7)).run(RecordedTarget({"a": GOOD["a"]}))
    assert tolerant.gate_passed is True


def test_gate_regression_against_a_baseline():
    gate = Gate(max_regression=0.1)
    suite = make_suite(gate)
    baseline = suite.run(RecordedTarget(GOOD))
    worse = suite.run(RecordedTarget({**GOOD, "b": "No idea."}), baseline=baseline)
    assert worse.baseline_run_id == baseline.id
    assert worse.gate_passed is False
    assert any("pass rate dropped 16.7%" in line for line in worse.gate_lines)
    assert suite.run(RecordedTarget(GOOD)).gate_lines == [
        "PASS error rate 0.0% ≤ 0.0%",
        "SKIP regression: no baseline run",
    ]


def test_json_round_trip_and_compare(tmp_path):
    suite = make_suite()
    a = suite.run(RecordedTarget({**GOOD, "c": "Costs $5."}))
    b = suite.run(RecordedTarget({**GOOD, "b": "No idea."}))
    path = es.write_report(a, tmp_path / "a.json")
    again = Run.from_json(path)
    assert again.id == a.id and again.summary == a.summary and len(again.results) == 6
    assert json.loads(path.read_text())["suite"] == "support"

    cmp = compare(again, b)
    assert cmp.same_dataset is True
    assert [(f.sample_id, f.check_key) for f in cmp.regressions] == [("b", "contains")]
    assert [(f.sample_id, f.check_key) for f in cmp.improvements] == [("c", "contains")]
    assert cmp.pass_rate_delta == pytest.approx(0.0)
    assert "regressions: 1  improvements: 1" in cmp.table()


def test_output_cost_is_counted_once_per_sample():
    run = Suite("s", dataset=DS, checks=[es.checks.length(), es.checks.contains()]).run(
        lambda q: Output(value="Within 30 days with the receipt, free.", cost_usd=0.1)
    )
    assert run.summary.cost_usd == pytest.approx(0.3)
