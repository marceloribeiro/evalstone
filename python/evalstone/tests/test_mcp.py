"""The MCP server: hermetic calls through the server object, plus one real stdio round
trip against the spawned `evalstone mcp` process (the observed effect)."""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import sys
import threading
from pathlib import Path

import pytest

from evalstone.mcp_server import Session, build_server

SAMPLE = Path(__file__).resolve().parents[3] / "samples" / "rag-bot"
EXE = Path(sys.executable).with_name("evalstone")


def _text(result) -> dict:
    assert result.is_error is False, result
    return json.loads(result.content[0].text)


def _call(server, name, **args):
    return _text(asyncio.run(server.call_tool(name, args)))


@pytest.fixture
def project(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from evalstone.cli import app

    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(app, ["init", "--project", "mcp-demo"]).exit_code == 0
    return tmp_path


def test_tools_are_listed_with_descriptions(project):
    server = build_server(project / "evalstone.yaml")
    tools = asyncio.run(server.list_tools())
    names = sorted(t.name for t in tools)
    assert names == [
        "compare_runs",
        "get_run",
        "judge_output",
        "list_suites",
        "record_sample",
        "run_suite",
    ]
    assert all(t.description for t in tools)


def test_list_run_get_compare_round_trip(project):
    server = build_server(project / "evalstone.yaml")
    listed = _call(server, "list_suites")
    assert listed["project"] == "mcp-demo" and "nightly" in listed["suites"]
    assert "no_apology" in listed["registered_checks"]
    assert "require_baseline" not in listed["suites"]["nightly"]["gate"]  # only shown when on

    run = _call(server, "run_suite", suite="nightly", report=str(project / "a.json"))
    assert run["summary"]["pass_rate"] == 1.0 and run["gate"]["passed"] is True
    assert run["report"].endswith("a.json") and Path(run["report"]).exists()

    outputs = project / "evals" / "outputs.jsonl"
    outputs.write_text(outputs.read_text().replace("3-5 business days", "a few days"))
    worse = _call(server, "run_suite", suite="nightly", report=str(project / "b.json"))
    assert worse["gate"]["passed"] is False and worse["failures_total"] == 1
    assert worse["failures"][0]["check"] == "must_include"

    cmp = _call(server, "compare_runs", a=str(project / "a.json"), b=str(project / "b.json"))
    assert len(cmp["regressions"]) == 1 and cmp["regressions"][0]["sample_id"] == "shipping"
    got = _call(server, "get_run", report=str(project / "b.json"))
    assert got["run_id"] == worse["run_id"]


def test_judge_output_and_record_sample(project):
    server = build_server(project / "evalstone.yaml")
    ok = _call(server, "judge_output", check="no_apology", output="Sure, here you go.")
    assert ok["passed"] is True and ok["kind"] == "deterministic"
    bad = _call(
        server,
        "judge_output",
        check="must_include",
        output="nope",
        expected={"must_include": ["x"]},
    )
    assert bad["passed"] is False and "missing" in bad["reason"]

    added = _call(
        server, "record_sample", dataset="golden", input="Do you ship abroad?", tags=["shipping"]
    )
    assert added["samples"] == 3 and added["dataset"] == "golden"
    dup = _call(server, "record_sample", dataset="golden", input="Do you ship abroad?")
    assert "already exists" in dup["error"]
    unknown = _call(server, "record_sample", dataset="nope", input="x")
    assert "unknown dataset" in unknown["error"]


def test_errors_are_returned_not_raised(tmp_path):
    server = build_server(tmp_path / "evalstone.yaml")
    assert "FileNotFoundError" in _call(server, "list_suites")["error"]
    assert "error" in _call(server, "run_suite", suite="x")
    assert "error" in _call(server, "get_run", report=str(tmp_path / "missing.json"))


def test_judge_output_takes_structured_outputs(project):
    """Trajectory checks read a dict; the `output` argument must not be typed as str."""
    cfg = project / "evalstone.yaml"
    cfg.write_text(
        cfg.read_text().replace(
            "checks:\n", "checks:\n  used_search: {type: trajectory.tool_called, name: search}\n"
        )
    )
    server = build_server(cfg)
    hit = _call(server, "judge_output", check="used_search", output={"steps": [{"tool": "search"}]})
    assert hit["passed"] is True, hit
    miss = _call(server, "judge_output", check="used_search", output={"steps": []})
    assert miss["passed"] is False


def test_relative_paths_resolve_against_the_project_root(project, tmp_path, monkeypatch):
    """A server started from another directory (or with --config) still writes and reads
    reports under the project, like the default report does."""
    elsewhere = tmp_path.parent / f"{tmp_path.name}-cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    server = build_server(project / "evalstone.yaml")
    run = _call(server, "run_suite", suite="nightly", report="runs/a.json")
    assert Path(run["report"]) == project / "runs" / "a.json" and Path(run["report"]).exists()
    assert not (elsewhere / "runs").exists()
    assert _call(server, "get_run", report="runs/a.json")["run_id"] == run["run_id"]
    cmp = _call(server, "compare_runs", a="runs/a.json", b="runs/a.json")
    assert cmp["regressions"] == []
    again = _call(server, "run_suite", suite="nightly", baseline="runs/a.json")
    assert again["gate"]["passed"] is True
    assert _call(server, "list_suites")["config"] == str(project / "evalstone.yaml")


def test_record_sample_repairs_a_missing_trailing_newline_and_keeps_utf8(project):
    golden = project / "evals" / "golden.jsonl"
    golden.write_text(golden.read_text().rstrip("\n"), encoding="utf-8")
    server = build_server(project / "evalstone.yaml")
    added = _call(server, "record_sample", dataset="golden", input="Posso devolver em promoção?")
    assert added["samples"] == 3, added
    text = golden.read_text(encoding="utf-8")
    assert text.count("\n") == 3 and text.endswith("\n")
    assert "promoção" in text and "\\u00e7" not in text
    assert _call(server, "list_suites")["project"] == "mcp-demo"  # the file still parses


def test_negative_failures_is_rejected_not_sliced(project):
    """`failures=-1` used to slice from the end and silently drop results."""
    from pydantic import ValidationError

    server = build_server(project / "evalstone.yaml")
    schemas = {t.name: t.input_schema for t in asyncio.run(server.list_tools())}
    assert schemas["run_suite"]["properties"]["failures"]["minimum"] == 0
    assert schemas["get_run"]["properties"]["failures"]["minimum"] == 0
    with pytest.raises(Exception) as info:  # the SDK's ToolError, caused by the validation
        asyncio.run(server.call_tool("run_suite", {"suite": "nightly", "failures": -1}))
    assert isinstance(info.value.__cause__, ValidationError)
    assert "failures" in str(info.value.__cause__)


def test_stray_stdout_from_a_check_module_goes_to_stderr(project, capsys):
    """Anything a check prints must not reach the protocol stream."""
    checks = project / "evals" / "checks.py"
    checks.write_text(checks.read_text() + '\nprint("hello from checks")\n')
    server = build_server(project / "evalstone.yaml")
    assert _call(server, "run_suite", suite="nightly")["gate"]["passed"] is True
    captured = capsys.readouterr()
    assert captured.out == "" and "hello from checks" in captured.err


def test_tool_calls_are_serialised(project):
    """The SDK runs sync tools on worker threads; two overlapping calls would race on
    the registry and the project's modules, so calls take turns."""
    checks = project / "evals" / "checks.py"
    checks.write_text(
        checks.read_text()
        + "\nimport time\nfrom evalstone import check as _c\n"
        + "@_c('slow')\ndef slow(sample, output):\n    t0 = time.perf_counter()\n"
        + "    time.sleep(0.05)\n"
        + "    with open('spans.txt', 'a') as fh:\n"
        + "        fh.write(f'{t0} {time.perf_counter()}\\n')\n"
        + "    return True\n"
    )
    cfg = project / "evalstone.yaml"
    cfg.write_text(cfg.read_text().replace("no_apology]", "no_apology, slow]"))
    server = build_server(cfg)
    errors: list[str] = []

    def one():
        out = _call(server, "run_suite", suite="nightly")
        if "error" in out:
            errors.append(out["error"])

    threads = [threading.Thread(target=one) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    lines = (project / "spans.txt").read_text().splitlines()
    spans = sorted(tuple(float(x) for x in line.split()) for line in lines)
    assert len(spans) == 6  # 3 runs x 2 samples
    for (_, end), (start, _) in itertools.pairwise(spans):
        assert start >= end  # no check ran while another call was still inside the lock


def test_session_keeps_one_provider_registry_until_the_config_changes(project):
    cfg = project / "evalstone.yaml"
    session = Session(cfg)
    first = session.config().provider_registry()
    assert session.config().provider_registry() is first

    closed = []

    class Fake:
        def close(self):
            closed.append(True)

    first.register("openai", Fake())
    cfg.write_text(cfg.read_text() + "judges: {default_model: openai/gpt-x}\n")
    second = session.config().provider_registry()
    assert second is not first and closed == [True]
    session.close()


def test_cli_only_swallows_the_missing_extra(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    import evalstone.cli as cli
    from evalstone.mcp_server import MissingExtra

    def boom(_config):
        raise RuntimeError("Event loop is closed")

    monkeypatch.setattr("evalstone.mcp_server.serve", boom)
    res = CliRunner().invoke(cli.app, ["mcp"])
    assert res.exit_code == 1 and isinstance(res.exception, RuntimeError)

    def missing(_config):
        raise MissingExtra("the MCP server needs the SDK: pip install 'evalstone[mcp]'")

    monkeypatch.setattr("evalstone.mcp_server.serve", missing)
    res = CliRunner().invoke(cli.app, ["mcp"])
    assert res.exit_code == 2 and "evalstone[mcp]" in res.output


@pytest.mark.skipif(not SAMPLE.exists(), reason="samples/rag-bot not checked out")
@pytest.mark.skipif(not EXE.exists(), reason="no evalstone console script next to python")
def test_real_stdio_server_round_trip(tmp_path):
    """Spawn `evalstone mcp` as a subprocess and talk MCP over stdio with the SDK client."""
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=str(EXE), args=["mcp"], cwd=str(SAMPLE), env={**os.environ}
    )
    report = str(tmp_path / "r.json")

    async def main():
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            listed = _text(await session.call_tool("list_suites", {}))
            args = {"suite": "nightly", "failures": 3, "report": report}
            run = _text(await session.call_tool("run_suite", args))
            return names, listed, run

    names, listed, run = asyncio.run(main())
    assert "run_suite" in names and listed["project"] == "rag-bot"
    assert run["summary"]["samples"] == 10 and run["gate"]["passed"] is False
    assert run["summary"]["pass_rate"] == 0.875 and len(run["failures"]) == 3
    assert run["report"] == report and Path(report).exists()
