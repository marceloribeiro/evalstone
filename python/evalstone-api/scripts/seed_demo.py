"""Seed a demo organization in a center from `samples/rag-bot` — what app.evalstone.com's
"Evalstone demo" organization holds.

    EVALSTONE_CENTER_URL=https://api.evalstone.com \\
    DEMO_EMAIL=demo@evalstone.com DEMO_PASSWORD=… \\
    python scripts/seed_demo.py

Registers the user when it does not exist (signs in otherwise), creates the organization
and the project (skipping ones that already exist by name), pushes the golden dataset,
runs the sample's deterministic suites through the library attached to the center, adds
three catalog checks, sets the ci run as the suite baseline, opens a grade queue over the
must_include failures and answers three tasks, creates a monitor and pushes 12 traces
answered by the sample's own bot (two deliberately weak) so a scoring pass opens an alert.
Idempotent enough to re-run; it never deletes anything. Needs the library (`evalstone`)
importable with the `samples/rag-bot` directory as the working directory.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

URL = os.environ.get("EVALSTONE_CENTER_URL", "http://localhost:8181").rstrip("/")
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

    org = (
        first(c.get("/organizations").json(), "name", ORG_NAME)
        or c.post("/organizations", json={"name": ORG_NAME}).raise_for_status().json()
    )
    project = (
        first(c.get(f"/organizations/{org['id']}/projects").json(), "name", PROJECT_NAME)
        or c.post(
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
    dataset = (
        first(c.get(f"/projects/{pid}/datasets").json(), "name", "golden")
        or c.post(
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
    say(
        "dataset golden v%s (%s samples) hash matches library: %s"
        % (v["version"], v["sample_count"], v["content_hash"] == ds.content_hash)
    )

    # the deterministic suites, run by the real library attached to this center
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "rag-bot"
        subprocess.run(["cp", "-R", str(SAMPLE), str(work)], check=True)
        (work / "evalstone.yaml").open("a").write(
            f"\ncenter:\n  url: {URL}\n  project: {pid}\n  api_key_env: EVALSTONE_API_KEY\n"
        )
        for suite in ("ci", "nightly"):
            out = subprocess.run(
                [sys.executable, "-m", "evalstone", "run", suite],
                cwd=work,
                env={**os.environ, "EVALSTONE_API_KEY": key},
                capture_output=True,
                text=True,
            )
            say(
                f"evalstone run {suite}:",
                (out.stdout + out.stderr).strip().splitlines()[-1]
                if (out.stdout + out.stderr).strip()
                else out.returncode,
            )

    # catalog checks (409 = already there)
    for body in (
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
    ):
        r = c.post(f"/organizations/{org['id']}/checks", json=body)
        say("check", body["key"], r.status_code)

    runs = c.get(f"/projects/{pid}/runs").json()["items"]
    ci = next((r for r in runs if r["suite"] == "ci"), None)
    if ci and not ci["is_baseline"]:
        c.put(f"/projects/{pid}/runs/{ci['id']}/baseline", json={}).raise_for_status()
        say("baseline: ci run", ci["client_run_id"])

    if ci and not first(
        c.get(f"/projects/{pid}/label-queues").json(), "name", "Grade the must_include failures"
    ):
        q = (
            c.post(
                f"/projects/{pid}/label-queues",
                json={
                    "name": "Grade the must_include failures",
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
        for grade in (2, 4, 1):
            t = c.post(f"/projects/{pid}/label-queues/{q['id']}/next").json()
            if not t:
                break
            c.post(
                f"/projects/{pid}/label-queues/{q['id']}/tasks/{t['id']}/answer",
                json={"grade": grade, "notes": "demo label"},
            ).raise_for_status()
        say("label queue:", q["task_count"], "tasks, 3 answered")

    monitor = (
        first(c.get(f"/projects/{pid}/monitors").json(), "name", "prod answers")
        or c.post(
            f"/projects/{pid}/monitors",
            json={
                "name": "prod answers",
                "check_keys": ["cites-policy", "no-apology", "short-answer"],
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
    from bot import answer

    traces = []
    for i, q in enumerate(QUESTIONS):
        out = answer(q)
        text = (
            "Sorry, unfortunately I'm not sure about that."
            if i in WEAK
            else (out.value if hasattr(out, "value") else str(out))
        )
        traces.append(
            {
                "id": f"demo-{i}",
                "input": q,
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
    c.post(f"/projects/{pid}/monitors/{monitor['id']}/score").raise_for_status()
    time.sleep(8)
    w = c.get(f"/projects/{pid}/monitors/{monitor['id']}/window").json()
    alerts = [a for a in c.get(f"/projects/{pid}/alerts").json() if a["resolved_at"] is None]
    say("traces stored", stored["stored"], "| window", json.dumps(w), "| open alerts", len(alerts))
    say("done:", f"{URL.replace('api.', 'app.')}/o/{org['id']}/p/{pid}")


def first(rows: list[dict], key: str, value: str) -> dict | None:
    return next((r for r in rows if r.get(key) == value), None)


def say(*parts: object) -> None:
    print("seed:", *parts, flush=True)


if __name__ == "__main__":
    main()
