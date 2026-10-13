"""The MCP server: hermetic calls through the server object, plus one real stdio round
trip against the spawned `evalstone mcp` process (the observed effect)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from evalstone.mcp_server import build_server

SAMPLE = Path(__file__).resolve().parents[3] / "samples" / "rag-bot"


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


@pytest.mark.skipif(not SAMPLE.exists(), reason="samples/rag-bot not checked out")
def test_real_stdio_server_round_trip():
    """Spawn `evalstone mcp` as a subprocess and talk MCP over stdio with the SDK client."""
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    exe = Path(sys.executable).with_name("evalstone")
    params = StdioServerParameters(
        command=str(exe), args=["mcp"], cwd=str(SAMPLE), env={**os.environ}
    )

    async def main():
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            listed = _text(await session.call_tool("list_suites", {}))
            run = _text(await session.call_tool("run_suite", {"suite": "nightly", "failures": 3}))
            return names, listed, run

    names, listed, run = asyncio.run(main())
    assert "run_suite" in names and listed["project"] == "rag-bot"
    assert run["summary"]["samples"] == 10 and run["gate"]["passed"] is False
    assert run["summary"]["pass_rate"] == 0.875 and len(run["failures"]) == 3
    (SAMPLE / "evalstone-report.json").unlink(missing_ok=True)
