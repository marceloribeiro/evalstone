import textwrap

import pytest

from evalstone import RecordedTarget, Suite
from evalstone.config import Config


@pytest.fixture
def project(tmp_path):
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "__init__.py").write_text("")
    (tmp_path / "evals" / "checks.py").write_text(
        textwrap.dedent(
            """
            from evalstone import check

            @check("polite")
            def polite(sample, output):
                return "please" in output.text.lower()
            """
        )
    )
    (tmp_path / "evals" / "golden.jsonl").write_text(
        '{"id": "a", "input": "q", "expected": {"must_include": ["x"]}}\n'
    )
    (tmp_path / "evals" / "outputs.jsonl").write_text('{"id": "a", "output": "x please"}\n')
    (tmp_path / "bot.py").write_text("def answer(q):\n    return 'x please'\n")
    (tmp_path / "evalstone.yaml").write_text(
        textwrap.dedent(
            """
            project: demo
            imports: [evals.checks]
            datasets:
              golden: evals/golden.jsonl
            checks:
              must_include: { type: contains }
              short: { type: length, max_words: 5 }
              no_ai: { type: regex, pattern: "as an ai", flags: 2, must_match: false }
            suites:
              recorded:
                dataset: golden
                target: { kind: recorded, path: evals/outputs.jsonl }
                checks: [must_include, short, polite, no_ai]
                gate: { min_pass_rate: 1.0 }
              live:
                dataset: golden
                target: { kind: callable, fn: "bot:answer" }
                checks: [must_include]
            """
        )
    )
    return tmp_path


def test_load_resolves_relative_to_the_config_file(project):
    cfg = Config.load(project)  # a directory works too
    assert cfg.project == "demo" and cfg.root == project.resolve()
    assert cfg.dataset("golden").content_hash
    with pytest.raises(KeyError, match="unknown dataset"):
        cfg.dataset("nope")


def test_keyed_checks_registered_checks_and_regex_pattern(project):
    cfg = Config.load(project / "evalstone.yaml")
    cfg.activate()
    assert cfg.check("must_include").key == "must_include"
    assert cfg.check("no_ai").key == "no_ai"
    assert cfg.check("polite").key == "polite"  # from imports
    with pytest.raises(KeyError, match="unknown check"):
        cfg.check("missing")


def test_check_type_validation(project):
    cfg = Config.load(project)
    cfg.checks["weird"] = {"type": "nope"}
    with pytest.raises(ValueError, match="unknown type"):
        cfg.check("weird")
    cfg.checks["untyped"] = {"max_words": 3}
    with pytest.raises(ValueError, match="needs a `type`"):
        cfg.check("untyped")


def test_suite_builds_with_recorded_and_callable_targets(project):
    cfg = Config.load(project)
    suite, target = cfg.suite("recorded")
    assert isinstance(suite, Suite) and isinstance(target, RecordedTarget)
    assert suite.check_keys == ["must_include", "short", "polite", "no_ai"]
    run = suite.run(target)
    assert run.summary.pass_rate == 1.0 and run.gate_passed is True

    live_suite, live_target = cfg.suite("live")
    assert live_target.describe()["kind"] == "callable"
    assert live_suite.run(live_target).summary.pass_rate == 1.0
    with pytest.raises(KeyError, match="unknown suite"):
        cfg.suite("nope")


def test_target_needs_a_kind_and_callable_needs_module_colon_attr(project, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("project: x\nsuites:\n  s: {dataset: d, target: {url: x}, checks: [a]}\n")
    with pytest.raises(ValueError, match="needs a `kind`"):
        Config.load(bad)
    cfg = Config.load(project)
    with pytest.raises(ValueError, match="module:function"):
        cfg.target({"kind": "callable", "fn": "bot.answer"})


def test_missing_config_points_at_init(tmp_path):
    with pytest.raises(FileNotFoundError, match="evalstone init"):
        Config.load(tmp_path)
