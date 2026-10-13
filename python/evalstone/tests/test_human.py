import json
import textwrap

import pytest
from typer.testing import CliRunner

import evalstone as es
from evalstone import Dataset, Output, RecordedTarget, Sample, Suite
from evalstone.checks.human import Label, LabelStore, human, output_hash
from evalstone.cli import app
from evalstone.config import Config

S = Sample(id="s1", input="q", expected={"must": ["x"]})


def test_label_store_round_trip_and_last_wins(tmp_path):
    path = tmp_path / "labels.jsonl"
    store = LabelStore(path)
    assert len(store) == 0 and store.get("s1", Output(value="a")) is None
    store.add(Label(sample_id="s1", output_hash=output_hash("a"), value=0.0, passed=False))
    h = output_hash("a")
    store.add(Label(sample_id="s1", output_hash=h, value=1.0, passed=True, notes="ok"))
    store.add(Label(sample_id="s1", output_hash=h, value=0.5, passed=True, check="tone"))
    again = LabelStore(path)
    assert len(again) == 2
    assert again.get("s1", Output(value="a")).notes == "ok"
    assert again.get("s1", Output(value="a"), check="tone").value == 0.5
    assert again.get("s1", Output(value="changed")) is None
    path.write_text("not json\n")
    with pytest.raises(ValueError, match="invalid label"):
        LabelStore(path)


def test_human_check_scores_from_labels_and_errors_when_unlabelled(tmp_path):
    path = tmp_path / "labels.jsonl"
    chk = human(labels=path)
    missing = chk(S, Output(value="answer"))
    assert missing.passed is False and missing.error.startswith("no human label for s1 @")
    LabelStore(path).add(
        Label(sample_id="s1", output_hash=output_hash("answer"), value=1.0, passed=True, raw="p")
    )
    good = chk(S, Output(value="answer"))
    assert good.passed and good.reason == "labelled pass" and good.raw["grade"] == "p"
    assert chk(S, Output(value="other")).error is not None  # changed output → not labelled
    assert chk.kind == "human" and es.checks.human is human
    suite = Suite("s", dataset=Dataset("d", [S]), checks=[chk, es.checks.length()])
    assert suite.check_keys == ["length", "human"]  # human is not a cheap check


def test_results_carry_input_and_expected_for_review():
    run = Suite("s", dataset=Dataset("d", [S]), checks=[es.checks.length()]).run(
        RecordedTarget({"s1": "answer"})
    )
    r = run.results[0]
    assert r.input == "q" and r.expected == {"must": ["x"]}
    assert json.loads(run.to_json())["results"][0]["input"] == "q"


def test_label_command_grades_resumes_and_feeds_the_human_check(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["run", "nightly", "--report", "r.json"]).exit_code == 0
    # first session: pass the first, quit
    args = ["label", "r.json", "--out", "labels.jsonl", "--labeler", "me"]
    res = runner.invoke(app, args, input="p\nlooks right\nq\n")
    assert res.exit_code == 0, res.output
    assert "2 output(s) to label" in res.output and "1 label(s) added" in res.output
    store = LabelStore("labels.jsonl")
    assert len(store) == 1 and next(iter(store)).labeler == "me"
    # second session resumes at the unlabelled one; bad grade re-prompts; fail it
    res = runner.invoke(app, args[:4], input="x\nf\nwrong window\n")
    assert res.exit_code == 0, res.output
    assert "1 output(s) to label" in res.output and "unrecognised grade" in res.output
    assert len(LabelStore("labels.jsonl")) == 2
    # a 1-5 scale with --check records a per-rubric grade
    scaled = [*args[:4], "--scale", "5", "--check", "tone"]
    res = runner.invoke(app, scaled, input="4\n\ns\n")
    assert res.exit_code == 0 and len(LabelStore("labels.jsonl")) == 3
    answer = "Yes — sale items can be returned within 30 days with a receipt."
    assert LabelStore("labels.jsonl").get("returns", answer, "tone").raw == 4

    # the human check reads the labels through the config
    cfg_path = tmp_path / "evalstone.yaml"
    cfg_path.write_text(
        cfg_path.read_text()
        + textwrap.dedent(
            """
            # appended by the test
            """
        )
    )
    cfg = Config.load(tmp_path)
    cfg.checks["reviewed"] = {"type": "human", "labels": "labels.jsonl"}
    cfg.suites["nightly"].checks = ["reviewed"]
    suite, target = cfg.suite("nightly")
    run = suite.run(target)
    by_id = {r.sample_id: r.score for r in run.results}
    assert by_id["returns"].passed is True and by_id["shipping"].passed is False
    assert by_id["shipping"].reason == "wrong window"
    assert runner.invoke(app, ["label", "r.json", "--scale", "1"]).exit_code == 2
