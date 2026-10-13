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


# ── review findings on PR 4 ──────────────────────────────────────────────────


def _project(root, mark, *, package=True):
    (root / "evals").mkdir()
    if package:
        (root / "evals" / "__init__.py").write_text("")
    (root / "evals" / "helpers.py").write_text(f"MARK = {mark!r}\n")
    (root / "evals" / "checks.py").write_text(
        textwrap.dedent(
            f"""
            from evalstone import check
            from evals import helpers

            MARK = {mark!r}

            @check("marked")
            def marked(sample, output):
                return helpers.MARK == {mark!r}
            """
        )
    )
    (root / "evalstone.yaml").write_text("project: p\nimports: [evals.checks]\n")
    return Config.load(root)


def test_activate_evicts_same_named_modules_from_a_prefix_sibling_root(tmp_path):
    import sys

    p2 = tmp_path / "p2"
    p = tmp_path / "p"
    p2.mkdir()
    p.mkdir()
    _project(p2, "p2").activate()
    assert sys.modules["evals.checks"].MARK == "p2"
    _project(p, "p").activate()
    assert sys.modules["evals.checks"].MARK == "p"
    assert sys.modules["evals.helpers"].MARK == "p"  # siblings evicted too, not only the chain


def test_activate_twice_works_for_namespace_packages(tmp_path):
    cfg = _project(tmp_path, "ns", package=False)
    cfg.activate()
    cfg.activate()
    from evalstone.checks import registry

    assert "marked" in registry


def test_check_types_are_an_allowlist_and_bad_kwargs_are_clear(project):
    cfg = Config.load(project)
    for bad in ("FunctionCheck", "deterministic", "_base", "Registry", "python"):
        cfg.checks["x"] = {"type": bad}
        with pytest.raises(ValueError, match="unknown type"):
            cfg.check("x")
    cfg.checks["short"] = {"type": "length", "max_word": 3}
    with pytest.raises(ValueError, match=r"check 'short' \(length\): .*max_word"):
        cfg.check("short")
    cfg.checks["rx"] = {"type": "regex"}
    with pytest.raises(ValueError, match="pattern"):
        cfg.check("rx")


def test_activate_reuses_the_module_until_it_changes_or_the_registry_is_cleared(tmp_path):
    import sys

    from evalstone.checks import registry

    cfg = _project(tmp_path, "one")
    cfg.activate()
    first = sys.modules["evals.checks"]
    cfg.activate()
    assert sys.modules["evals.checks"] is first  # unchanged project: same module object

    helpers = tmp_path / "evals" / "helpers.py"
    helpers.write_text("MARK = 'two'  # edited\n")  # a new size: no stale .pyc within the second
    cfg.activate()
    assert sys.modules["evals.checks"] is not first  # a sibling file changed: fresh import
    second = sys.modules["evals.checks"]
    assert second.helpers.MARK == "two"

    registry.clear()
    cfg.activate()
    assert sys.modules["evals.checks"] is not second and "marked" in registry


def test_activate_keeps_a_module_the_caller_imported_from_this_root(tmp_path, monkeypatch):
    import importlib
    import sys

    _project(tmp_path, "mine")
    for name in [n for n in sys.modules if n == "evals" or n.startswith("evals.")]:
        monkeypatch.delitem(sys.modules, name)  # another test's project of the same name
    monkeypatch.syspath_prepend(str(tmp_path))
    mod = importlib.import_module("evals.checks")
    mod.MARK = "patched"
    Config.load(tmp_path).activate()
    assert sys.modules["evals.checks"] is mod and sys.modules["evals.checks"].MARK == "patched"
