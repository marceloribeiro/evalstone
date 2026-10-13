"""The composite GitHub Action: its shell step run for real against samples/rag-bot
(inputs through the environment, outputs read back), and a static guard against
interpolating inputs into scripts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
ACTION = ROOT / "action" / "action.yml"
SAMPLE = ROOT / "samples" / "rag-bot"
EXE = Path(sys.executable).with_name("evalstone")


def _steps() -> list[dict]:
    return yaml.safe_load(ACTION.read_text())["runs"]["steps"]


def test_no_input_is_interpolated_into_a_script():
    """`${{ inputs.x }}` inside `run:`/`script:` is a shell/JS injection; inputs go via env."""
    for step in _steps():
        script = step.get("run") or step.get("with", {}).get("script") or ""
        assert "${{" not in script, f"step {step.get('name')!r} interpolates into its script"
        for key, value in step.get("env", {}).items():
            assert isinstance(value, str), key


def test_inputs_and_defaults_are_consistent_with_the_cli():
    from evalstone.run import DEFAULT_FAILURES

    inputs = yaml.safe_load(ACTION.read_text())["inputs"]
    assert inputs["failures"]["default"] == str(DEFAULT_FAILURES)
    assert inputs["report"]["default"] == ""  # → the runner's temp dir, see the run step
    assert "comment-id" in inputs


@pytest.mark.skipif(not SAMPLE.exists(), reason="samples/rag-bot not checked out")
@pytest.mark.skipif(not EXE.exists(), reason="no evalstone console script next to python")
def test_run_step_against_the_sample(tmp_path):
    """Execute the 'Run the suite' step's script as the runner would."""
    step = next(s for s in _steps() if s.get("id") == "run")
    temp = tmp_path / "runner-temp"
    temp.mkdir()
    out = tmp_path / "output.txt"
    summary = tmp_path / "summary.md"
    out.touch()
    summary.touch()
    env = {
        **os.environ,
        "PATH": f"{EXE.parent}{os.pathsep}{os.environ.get('PATH', '')}",
        "SUITE": "ci",
        "CONFIG": "evalstone.yaml",
        "BASELINE": "",
        "REPORT": "",
        "FAILURES": "2",
        "RUNNER_TEMP": str(temp),
        "GITHUB_OUTPUT": str(out),
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    res = subprocess.run(
        ["bash", "-c", step["run"]], cwd=SAMPLE, env=env, capture_output=True, text=True
    )
    assert res.returncode == 0, res.stdout + res.stderr
    outputs = dict(line.split("=", 1) for line in out.read_text().splitlines())
    assert outputs["passed"] == "true"
    assert outputs["report"] == str(
        temp / "evalstone-report.json"
    )  # absolute, outside the checkout
    assert Path(outputs["comment"]).read_text().startswith("### Evalstone · `ci` — ✅ gate passed")
    assert summary.read_text() == Path(outputs["comment"]).read_text()
    assert not (SAMPLE / "evalstone-comment.md").exists()
    assert not (SAMPLE / "evalstone-report.json").exists()

    # the report output feeds a later run's baseline, and a relative report lands in the cwd
    env.update({"BASELINE": outputs["report"], "REPORT": str(tmp_path / "second.json")})
    env["SUITE"] = "nightly"
    out.write_text("")
    res = subprocess.run(
        ["bash", "-c", step["run"]], cwd=SAMPLE, env=env, capture_output=True, text=True
    )
    assert res.returncode == 0, res.stdout + res.stderr
    outputs = dict(line.split("=", 1) for line in out.read_text().splitlines())
    assert outputs["passed"] == "false" and outputs["report"] == str(tmp_path / "second.json")
    from evalstone.run import Run

    first = Run.from_json(temp / "evalstone-report.json")
    second = Run.from_json(tmp_path / "second.json")
    assert second.baseline_run_id == first.id  # the first run's output fed the second's baseline
    assert (
        Path(outputs["comment"])
        .read_text()
        .startswith("### Evalstone · `nightly` — ❌ gate failed")
    )


def test_sample_ci_suite_is_nightly_with_a_lower_bar():
    cfg = yaml.safe_load((SAMPLE / "evalstone.yaml").read_text())
    nightly, ci = cfg["suites"]["nightly"], cfg["suites"]["ci"]
    assert {k: v for k, v in ci.items() if k != "gate"} == {
        k: v for k, v in nightly.items() if k != "gate"
    }
    assert ci["gate"] == {"min_pass_rate": 0.85} and nightly["gate"]["min_pass_rate"] == 0.9
