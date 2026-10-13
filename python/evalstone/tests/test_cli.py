import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from evalstone.cli import app

runner = CliRunner()
SAMPLE = Path(__file__).resolve().parents[3] / "samples" / "rag-bot"


@pytest.fixture
def in_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_version():
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0 and "evalstone 0." in res.output


def test_init_then_run_then_gate_then_show(in_dir):
    res = runner.invoke(app, ["init", "--project", "demo"])
    assert res.exit_code == 0, res.output
    assert (in_dir / "evalstone.yaml").exists() and (in_dir / "evals" / "golden.jsonl").exists()
    assert runner.invoke(app, ["init"]).exit_code == 2  # refuses to overwrite

    res = runner.invoke(app, ["run", "nightly", "--report", "r.json"])
    assert res.exit_code == 0, res.output
    assert "must_include" in res.output and "gate PASSED" in res.output
    report = json.loads(Path("r.json").read_text())
    assert report["summary"]["pass_rate"] == 1.0 and report["gate_passed"] is True

    assert runner.invoke(app, ["gate", "nightly", "--report", "g.json"]).exit_code == 0
    res = runner.invoke(app, ["show", "r.json"])
    assert res.exit_code == 0 and "total" in res.output
    res = runner.invoke(app, ["list"])
    assert res.exit_code == 0 and "suite nightly" in res.output and "no_apology" in res.output


def test_gate_exits_1_and_compare_reports_regressions(in_dir):
    runner.invoke(app, ["init"])
    runner.invoke(app, ["run", "nightly", "--report", "a.json"])
    # break one recorded output, run again
    outputs = Path("evals/outputs.jsonl")
    outputs.write_text(outputs.read_text().replace("3-5 business days", "a few days"))
    res = runner.invoke(app, ["run", "nightly", "--report", "b.json"])
    assert res.exit_code == 0 and "gate FAILED" in res.output
    assert "missing ['3-5']" in res.output
    assert runner.invoke(app, ["run", "nightly", "--strict", "--report", "c.json"]).exit_code == 1
    assert runner.invoke(app, ["gate", "nightly", "--report", "d.json"]).exit_code == 1

    res = runner.invoke(app, ["compare", "a.json", "b.json"])
    assert res.exit_code == 1 and "regressions: 1" in res.output
    assert "shipping must_include" in res.output
    assert runner.invoke(app, ["compare", "a.json", "a.json"]).exit_code == 0


def test_run_with_baseline_gates_regression(in_dir):
    runner.invoke(app, ["init"])
    cfg = Path("evalstone.yaml")
    cfg.write_text(
        cfg.read_text().replace("gate: {min_pass_rate: 0.9}", "gate: {max_regression: 0.0}")
    )
    runner.invoke(app, ["run", "nightly", "--report", "base.json"])
    outputs = Path("evals/outputs.jsonl")
    outputs.write_text(outputs.read_text().replace("30 days", "a month"))
    res = runner.invoke(app, ["gate", "nightly", "--report", "x.json", "--baseline", "base.json"])
    assert res.exit_code == 1 and "pass rate dropped" in res.output


def test_errors_are_reported_with_exit_2(in_dir):
    assert runner.invoke(app, ["run", "nightly"]).exit_code == 2  # no config
    runner.invoke(app, ["init"])
    res = runner.invoke(app, ["run", "nope"])
    assert res.exit_code == 2 and "unknown suite" in res.output


@pytest.mark.skipif(not SAMPLE.exists(), reason="samples/rag-bot not checked out")
def test_rag_bot_sample_runs_end_to_end(monkeypatch, tmp_path):
    monkeypatch.chdir(SAMPLE)
    res = runner.invoke(app, ["run", "nightly", "--report", str(tmp_path / "rag.json")])
    assert res.exit_code == 0, res.output
    report = json.loads((tmp_path / "rag.json").read_text())
    assert report["summary"]["samples"] == 10 and report["summary"]["errors"] == 0
    assert report["summary"]["per_check"][0]["key"] == "must_include"
    assert os.path.basename(report["target"]["name"]) == "answer"


# ── review findings on PR 4 ──────────────────────────────────────────────────


def test_config_and_report_problems_exit_2_with_a_message(in_dir):
    Path("evalstone.yaml").write_text(
        "project: x\nsuites:\n  s: {dataset: d, target: {url: x}, checks: [a]}\n"
    )
    res = runner.invoke(app, ["run", "s"])
    assert res.exit_code == 2 and "kind" in res.output
    Path("evalstone.yaml").write_text("\tproject: x\n")
    assert runner.invoke(app, ["list"]).exit_code == 2
    Path("evalstone.yaml").unlink()
    runner.invoke(app, ["init"])
    Path("evals/golden.jsonl").unlink()
    res = runner.invoke(app, ["run", "nightly"])
    assert res.exit_code == 2 and "golden.jsonl" in res.output
    assert runner.invoke(app, ["show", "missing.json"]).exit_code == 2
    assert runner.invoke(app, ["compare", "missing.json", "missing.json"]).exit_code == 2
    assert runner.invoke(app, ["run", "nightly", "--baseline", "nope.json"]).exit_code == 2


def test_init_never_overwrites_and_quotes_the_project_name(in_dir):
    Path("evals").mkdir()
    Path("evals/checks.py").write_text("# MY CUSTOM CHECKS\n")
    res = runner.invoke(app, ["init"])
    assert res.exit_code == 2 and "refusing to overwrite" in res.output
    assert Path("evals/checks.py").read_text() == "# MY CUSTOM CHECKS\n"
    assert not Path("evalstone.yaml").exists()
    Path("evals/checks.py").unlink()
    res = runner.invoke(app, ["init", "--project", "acme: support #1"])
    assert res.exit_code == 0, res.output
    assert runner.invoke(app, ["list"]).exit_code == 0
    assert runner.invoke(app, ["run", "nightly", "--report", "r.json"]).exit_code == 0


def test_show_markdown(in_dir):
    runner.invoke(app, ["init"])
    runner.invoke(app, ["run", "nightly", "--report", "r.json"])
    res = runner.invoke(app, ["show", "r.json", "--markdown"])
    assert res.exit_code == 0 and res.output.startswith(
        "### Evalstone · `nightly` — ✅ gate passed"
    )
    assert "| `must_include` |" in res.output
