"""The pytest plugin, exercised through pytest's own `pytester` in a scratch project."""

from __future__ import annotations

import pytest

from evalstone.cli import app

pytest.importorskip("evalstone.pytest_plugin")


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
    assert (project.path / "evalstone-report.json").exists()


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
    result = project.runpytest(
        "-p",
        "no:cacheprovider",
        "--evalstone-config",
        str(cfg),
        "--evalstone-baseline",
        str(sub / "evalstone-report.json"),
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
