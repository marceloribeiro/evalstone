"""The pytest plugin, exercised through pytest's own `pytester` in a scratch project."""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys

import pytest

from evalstone.cli import app


@pytest.fixture(autouse=True, scope="module")
def _plugin_entry_point_installed():
    """The inner pytest sessions find the plugin through the installed distribution's
    `pytest11` entry point; a stale editable install fails every test here with
    `fixture 'evalstone_run' not found`, so say why up front."""
    names = {ep.name for ep in importlib.metadata.entry_points(group="pytest11")}
    if "evalstone" not in names:
        pytest.fail("evalstone's pytest11 entry point is not installed: run pip install -e .")


@pytest.fixture
def project(pytester: pytest.Pytester):
    from typer.testing import CliRunner

    assert CliRunner().invoke(app, ["init", str(pytester.path), "--project", "pt"]).exit_code == 0
    return pytester


def test_suite_decorator_runs_the_suite_and_gates(project: pytest.Pytester):
    project.makepyfile(
        test_evals="""
        from evalstone.pytest_plugin import suite

        @suite("nightly")
        def test_nightly(run):
            assert run.summary.samples == 2
            assert run.trigger == "ci"

        @suite("nightly", gate=False)
        def test_without_body():
            pass
        """
    )
    result = project.runpytest("-p", "no:cacheprovider", "-v")
    result.assert_outcomes(passed=2)
    assert (project.path / "evalstone-report.nightly.json").exists()
    assert not (project.path / "evalstone-report.json").exists()


def test_gate_failure_fails_the_test_with_the_report(project: pytest.Pytester):
    outputs = project.path / "evals" / "outputs.jsonl"
    outputs.write_text(outputs.read_text().replace("3-5 business days", "a few days"))
    project.makepyfile(
        test_evals="""
        from evalstone.pytest_plugin import suite

        @suite("nightly")
        def test_nightly(run):
            raise AssertionError("body must not run when the gate fails")

        def test_fixture_form(evalstone_gate):
            evalstone_gate("nightly")

        def test_run_without_gate(evalstone_run):
            run = evalstone_run("nightly")
            assert run.gate_passed is False
        """
    )
    result = project.runpytest("-p", "no:cacheprovider")
    result.assert_outcomes(passed=1, failed=2)
    result.stdout.fnmatch_lines(["*evalstone gate FAILED for suite 'nightly'*"])
    result.stdout.fnmatch_lines(["*FAIL pass rate*"])
    result.stdout.fnmatch_lines(["*shipping · must_include · missing*3-5*"])
    assert "body must not run" not in result.stdout.str()


def test_config_option_and_baseline_regression(project: pytest.Pytester):
    sub = project.mkdir("elsewhere")
    for name in ("evalstone.yaml", "evals"):
        (project.path / name).rename(sub / name)
    project.makepyfile(
        test_evals="""
        def test_baseline(evalstone_run):
            run = evalstone_run("nightly")
            assert run.summary.pass_rate == 1.0
        """
    )
    result = project.runpytest(
        "-p", "no:cacheprovider", "--evalstone-config", str(sub / "evalstone.yaml")
    )
    result.assert_outcomes(passed=1)
    # the report just written becomes the baseline for a regressing run
    baselines = project.mkdir("baselines")
    (sub / "evalstone-report.nightly.json").rename(baselines / "evalstone-report.nightly.json")
    outputs = sub / "evals" / "outputs.jsonl"
    outputs.write_text(outputs.read_text().replace("30 days", "a month"))
    cfg = sub / "evalstone.yaml"
    cfg.write_text(
        cfg.read_text().replace("gate: {min_pass_rate: 0.9}", "gate: {max_regression: 0.0}")
    )
    project.makepyfile(
        test_evals="""
        def test_regression(evalstone_gate):
            evalstone_gate("nightly")
        """
    )
    for baseline in ("../baselines/evalstone-report.nightly.json", "../baselines", str(baselines)):
        # a file or a directory of per-suite reports; relative to the config's dir
        result = project.runpytest(
            "-p",
            "no:cacheprovider",
            "--evalstone-config",
            str(cfg),
            "--evalstone-baseline",
            baseline,
        )
        result.assert_outcomes(failed=1)
        result.stdout.fnmatch_lines(["*pass rate dropped*"])


def test_missing_config_skips_instead_of_erroring(pytester: pytest.Pytester):
    pytester.makepyfile(
        test_evals="""
        def test_x(evalstone_run):
            evalstone_run("nightly")
        """
    )
    pytester.runpytest("-p", "no:cacheprovider").assert_outcomes(skipped=1)


def test_suite_decorator_on_a_test_method(project: pytest.Pytester):
    project.makepyfile(
        test_evals="""
        from evalstone.pytest_plugin import suite

        class TestEvals:
            @suite("nightly")
            def test_with_run(self, run, tmp_path):
                assert run.summary.samples == 2 and tmp_path.is_dir()

            @suite("nightly", gate=False)
            def test_without(self):
                pass
        """
    )
    project.runpytest("-p", "no:cacheprovider").assert_outcomes(passed=2)


def test_patches_made_in_the_test_reach_the_target(project: pytest.Pytester, monkeypatch):
    """Running a suite must not re-import the project's modules behind the test's back."""
    monkeypatch.delitem(sys.modules, "bot", raising=False)  # another test's `bot` namesake
    (project.path / "bot.py").write_text(
        "def client(question):\n    return 'the real model'\n\n"
        "def answer(question):\n    return client(question)\n"
    )
    cfg = project.path / "evalstone.yaml"
    cfg.write_text(
        cfg.read_text()
        + "  live:\n    dataset: golden\n    target: {kind: callable, fn: 'bot:answer'}\n"
        "    checks: [must_include]\n    gate: {min_pass_rate: 1.0}\n"
    )
    project.makepyfile(
        test_evals="""
        import bot
        from evalstone.pytest_plugin import suite

        def test_patched(monkeypatch, evalstone_gate):
            monkeypatch.setattr(bot, "client", lambda q: "within 30 days, 3-5 business days")
            run = evalstone_gate("live")
            assert run.summary.pass_rate == 1.0

        def test_unpatched(evalstone_run):
            assert evalstone_run("live").summary.pass_rate == 0.0
        """
    )
    project.runpytest("-p", "no:cacheprovider").assert_outcomes(passed=2)


def test_each_suite_writes_its_own_report(project: pytest.Pytester):
    cfg = project.path / "evalstone.yaml"
    cfg.write_text(
        cfg.read_text()
        + "  smoke:\n    dataset: golden\n    target: {kind: recorded, path: evals/outputs.jsonl}\n"
        "    checks: [short]\n    gate: {min_pass_rate: 0.5}\n"
    )
    project.makepyfile(
        test_evals="""
        from evalstone.pytest_plugin import suite

        @suite("nightly")
        def test_nightly(run):
            pass

        @suite("smoke")
        def test_smoke(run):
            pass

        def test_explicit(evalstone_run):
            evalstone_run("smoke", report="reports/smoke.json")
        """
    )
    project.runpytest("-p", "no:cacheprovider").assert_outcomes(passed=3)
    from evalstone.run import Run

    nightly = Run.from_json(project.path / "evalstone-report.nightly.json")
    smoke = Run.from_json(project.path / "evalstone-report.smoke.json")
    assert (nightly.suite, smoke.suite) == ("nightly", "smoke")
    assert Run.from_json(project.path / "reports" / "smoke.json").suite == "smoke"


def test_a_suite_without_a_gate_cannot_pass_the_gate_fixture(project: pytest.Pytester):
    cfg = project.path / "evalstone.yaml"
    cfg.write_text(cfg.read_text().replace("    gate: {min_pass_rate: 0.9}\n", ""))
    project.makepyfile(
        test_evals="""
        from evalstone.pytest_plugin import suite

        @suite("nightly")
        def test_decorated():
            pass

        def test_fixture(evalstone_gate):
            evalstone_gate("nightly")

        def test_run_is_fine(evalstone_run):
            assert evalstone_run("nightly").gate_passed is None
        """
    )
    result = project.runpytest("-p", "no:cacheprovider")
    result.assert_outcomes(passed=1, failed=2)
    result.stdout.fnmatch_lines(["*suite 'nightly' has no gate*"])


def test_plugin_module_imports_only_pytest():
    """It loads into every pytest session on the interpreter, so evalstone's own
    modules (checks, providers, pydantic models) must not be imported until used."""
    code = (
        "import sys, evalstone.pytest_plugin; "
        "print(sorted(m for m in sys.modules if m.startswith('evalstone.')))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "['evalstone.pytest_plugin']", out.stdout
