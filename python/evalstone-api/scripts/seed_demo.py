"""Seed a demo organization in a center from `samples/rag-bot` — what app.evalstone.com's
"Evalstone demo" organization holds.

    EVALSTONE_CENTER_URL=https://api.evalstone.com EVALSTONE_WEB_URL=https://app.evalstone.com \\
    DEMO_EMAIL=demo@evalstone.com DEMO_PASSWORD=… \\
    python scripts/seed_demo.py

Registers the user when it does not exist (signs in otherwise), creates the organization
and the project (reusing ones that exist by name), pushes the golden dataset, runs the
sample's deterministic suites through the library attached to the center, adds three catalog
checks, sets the ci run as the suite baseline, opens a grade queue over the must_include
failures and answers three tasks, creates a monitor and pushes 12 traces answered by the
sample's own bot (two deliberately weak) so a scoring pass opens an alert.

Re-runnable: existing rows are reused and the previous seed key is revoked; nothing else is
deleted. Exits non-zero the moment a step does not do what it says. Needs the library
(`evalstone`) importable; `samples/rag-bot` is located from this file (or RAG_BOT_DIR).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

URL = os.environ.get("EVALSTONE_CENTER_URL", "http://localhost:8181").rstrip("/")
WEB_URL = os.environ.get("EVALSTONE_WEB_URL", "http://localhost:8182").rstrip("/")
EMAIL = os.environ.get("DEMO_EMAIL", "demo@evalstone.com")
PASSWORD = os.environ.get("DEMO_PASSWORD", "")
ORG_NAME = os.environ.get("DEMO_ORG_NAME", "Evalstone demo")
PROJECT_NAME = os.environ.get("DEMO_PROJECT_NAME", "rag-bot")
SAMPLE = Path(
    os.environ.get("RAG_BOT_DIR", Path(__file__).resolve().parents[3] / "samples" / "rag-bot")
)

QUESTIONS = [
    "How many days do I have to return something?",
    "Is shipping free?",
    "How long is the warranty?",
    "Can I exchange a gift?",
    "Do you ship to the UK?",
    "How do I track my order?",
    "What is your refund time?",
    "Can I return sale items?",
    "Do I need the receipt?",
    "How much is express shipping?",
    "Can I cancel an order?",
    "Do you price match?",
]
WEAK = {3, 11}  # two traces answered badly on purpose, so the monitor has something to flag

CHECKS = [
    {
        "key": "cites-policy",
        "type": "contains",
        "params": {
            "needles": [
                "days",
                "receipt",
                "shipping",
                "warranty",
                "refund",
                "return",
                "exchange",
                "order",
            ],
            "require_all": False,
        },
        "description": "The answer names a concrete policy term",
    },
    {
        "key": "no-apology",
        "type": "safety.forbidden",
        "params": {"phrases": ["sorry", "apologize", "unfortunately"]},
        "description": "Support answers state the rule; they do not apologise for it",
    },
    {
        "key": "short-answer",
        "type": "length",
        "params": {"max_chars": 280},
        "description": "One or two sentences",
    },
]


def main() -> None:
    if not PASSWORD:
        sys.exit("set DEMO_PASSWORD")
    c = httpx.Client(base_url=URL, timeout=120)
    r = c.post(
        "/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "first_name": "Evalstone", "last_name": "Demo"},
    )
    if r.status_code == 409:
        r = c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    c.headers["authorization"] = f"Bearer {r.json()['token']}"
    say("signed in as", EMAIL)

    org = first(c.get("/organizations").json(), "name", ORG_NAME)
    if org is None:
        org = c.post("/organizations", json={"name": ORG_NAME}).raise_for_status().json()
    projects = c.get(f"/organizations/{org['id']}/projects").json()
    project = first(projects, "name", PROJECT_NAME)
    if project is None:
        project = (
            c.post(
                f"/organizations/{org['id']}/projects",
                json={
                    "name": PROJECT_NAME,
                    "description": "The sample support bot from samples/rag-bot, "
                    "evaluated against its golden set",
                },
            )
            .raise_for_status()
            .json()
        )
    pid = project["id"]
    say("organization", org["id"], "project", pid)
    for old in c.get(f"/projects/{pid}/ingest-keys").raise_for_status().json():
        if old["name"] == "demo-seed" and not old["revoked_at"]:
            c.delete(f"/projects/{pid}/ingest-keys/{old['id']}").raise_for_status()
    key = (
        c.post(f"/projects/{pid}/ingest-keys", json={"name": "demo-seed"})
        .raise_for_status()
        .json()["key"]
    )

    # the golden dataset, pushed as the library would hash it
    sys.path.insert(0, str(SAMPLE))
    from evalstone.config import Config

    cfg = Config.load(str(SAMPLE / "evalstone.yaml"))
    ds = cfg.dataset("golden")
    dataset = first(c.get(f"/projects/{pid}/datasets").json(), "name", "golden")
    if dataset is None:
        dataset = (
            c.post(
                f"/projects/{pid}/datasets",
                json={
                    "name": "golden",
                    "description": "Hand-written answers for the support bot "
                    "(samples/rag-bot/evals/golden.jsonl)",
                    "tags": ["golden", "sample"],
                },
            )
            .raise_for_status()
            .json()
        )
    records = [
        {
            "id": s.id,
            "input": s.input,
            "expected": s.expected,
            "metadata": s.metadata,
            "tags": list(s.tags),
        }
        for s in ds.samples
    ]
    v = (
        c.post(
            f"/projects/{pid}/datasets/{dataset['id']}/versions",
            json={"samples": records, "note": "golden.jsonl as shipped in samples/rag-bot"},
        )
        .raise_for_status()
        .json()
    )
    if v["content_hash"] != ds.content_hash:
        sys.exit(f"dataset hash mismatch: center {v['content_hash']} vs library {ds.content_hash}")
    say(f"dataset golden v{v['version']} ({v['sample_count']} samples), hash matches the library")

    # the deterministic suites, run by the real library attached to this center
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "rag-bot"
        shutil.copytree(
            SAMPLE, work, ignore=shutil.ignore_patterns("__pycache__", "evalstone-report.json")
        )
        cfg_path = work / "evalstone.yaml"
        cfg_path.write_text(
            cfg_path.read_text()
            + f"\ncenter:\n  url: {URL}\n  project: {pid}\n  api_key_env: EVALSTONE_API_KEY\n"
        )
        for suite in ("ci", "nightly"):
            out = subprocess.run(
                [sys.executable, "-m", "evalstone", "run", suite],
                cwd=work,
                env={**os.environ, "EVALSTONE_API_KEY": key},
                capture_output=True,
                text=True,
            )
            text = (out.stdout + out.stderr).strip()
            # ci's gate passes, nightly's fails by design (exit 1); anything else is an error
            if out.returncode not in (0, 1) or "stored" not in text:
                sys.exit(f"evalstone run {suite} failed (exit {out.returncode}):\n{text[-800:]}")
            say(f"evalstone run {suite}:", text.splitlines()[-1])

    for body in CHECKS:
        r = c.post(f"/organizations/{org['id']}/checks", json=body)
        if r.status_code not in (201, 409):
            sys.exit(f"check {body['key']}: {r.status_code} {r.text}")
        say("check", body["key"], "created" if r.status_code == 201 else "exists")

    runs = c.get(f"/projects/{pid}/runs").json()["items"]
    ci = next((r for r in runs if r["suite"] == "ci"), None)
    if ci is None:
        sys.exit("no ci run stored")
    if not ci["is_baseline"]:
        c.put(f"/projects/{pid}/runs/{ci['id']}/baseline", json={}).raise_for_status()
        say("baseline: ci run", ci["client_run_id"])

    queue_name = "Grade the must_include failures"
    if first(c.get(f"/projects/{pid}/label-queues").json(), "name", queue_name) is None:
        q = (
            c.post(
                f"/projects/{pid}/label-queues",
                json={
                    "name": queue_name,
                    "kind": "grade",
                    "source": {
                        "run_id": ci["id"],
                        "check_key": "must_include",
                        "failed_only": True,
                    },
                    "instructions": "Did the bot actually answer the customer's question? "
                    "5 = fully, 1 = not at all.",
                    "check_key": "helpful",
                    "scale": 5,
                },
            )
            .raise_for_status()
            .json()
        )
        answered = 0
        for grade in (2, 4, 1):
            t = c.post(f"/projects/{pid}/label-queues/{q['id']}/next").json()
            if not t:
                break
            c.post(
                f"/projects/{pid}/label-queues/{q['id']}/tasks/{t['id']}/answer",
                json={"grade": grade, "notes": "demo label"},
            ).raise_for_status()
            answered += 1
        say("label queue:", q["task_count"], "tasks,", answered, "answered")

    monitor = first(c.get(f"/projects/{pid}/monitors").json(), "name", "prod answers")
    if monitor is None:
        monitor = (
            c.post(
                f"/projects/{pid}/monitors",
                json={
                    "name": "prod answers",
                    "check_keys": [b["key"] for b in CHECKS],
                    "sample_rate": 1.0,
                    "alert_policy": {
                        "metric": "pass_rate",
                        "threshold": 0.9,
                        "window_minutes": 1440,
                        "min_n": 10,
                    },
                },
            )
            .raise_for_status()
            .json()
        )
    from bot import answer  # the sample's bot

    traces = []
    for i, question in enumerate(QUESTIONS):
        out = answer(question)
        text = out.value if hasattr(out, "value") else str(out)
        if i in WEAK:
            text = "Sorry, unfortunately I'm not sure about that."
        traces.append(
            {
                "id": f"demo-{i}",
                "input": question,
                "output": text,
                "tags": ["prod", "demo"],
                "model": "gpt-4o-mini",
                "latency_ms": 180 + i * 7,
            }
        )
    stored = (
        httpx.post(
            f"{URL}/projects/{pid}/traces",
            json={"traces": traces},
            headers={"authorization": f"Bearer {key}"},
            timeout=60,
        )
        .raise_for_status()
        .json()
    )
    if stored["stored"]:  # a re-run stores nothing (traces dedupe by id): nothing new to score
        before = monitor.get("last_scored_at")
        c.post(f"/projects/{pid}/monitors/{monitor['id']}/score").raise_for_status()
        for _ in range(60):  # the worker scores it; wait for the pass to be recorded
            time.sleep(1)
            m = c.get(f"/projects/{pid}/monitors/{monitor['id']}").json()
            if m.get("last_error"):
                sys.exit(f"monitor scoring failed: {m['last_error']}")
            if m.get("last_scored_at") and m["last_scored_at"] != before:
                break
        else:
            sys.exit("monitor was not scored within 60 s — is the Celery worker running?")
    w = c.get(f"/projects/{pid}/monitors/{monitor['id']}/window").json()
    alerts = [a for a in c.get(f"/projects/{pid}/alerts").json() if a["resolved_at"] is None]
    say("traces stored", stored["stored"], "| window", json.dumps(w), "| open alerts", len(alerts))
    say("done:", f"{WEB_URL}/o/{org['id']}/p/{pid}")


def first(rows: list[dict], key: str, value: str) -> dict | None:
    return next((r for r in rows if r.get(key) == value), None)


def say(*parts: object) -> None:
    print("seed:", *parts, flush=True)


if __name__ == "__main__":
    main()
