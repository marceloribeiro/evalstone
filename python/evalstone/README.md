# evalstone

The plug-and-play evals layer for LLM-based projects, as a Python library.

> **Status:** 0.1.0 — release candidate. Until it is on PyPI, install from the
> repo: `pip install -e python/evalstone`. Docs: [evalstone.com/docs/evalstone/library](https://evalstone.com/docs/evalstone/library).

The library **computes**; it owns no database. A run lives in memory, prints a
table and writes a JSON report. Persistence happens through the Evalstone
center (PostgreSQL) when one is configured.

## Develop

```bash
just install     # venv + editable install with dev extras
just check       # ruff + pytest
just console     # REPL with `es` loaded
```

## Quick start

```bash
pip install -e python/evalstone          # or, once published: pip install evalstone
cd samples/rag-bot
evalstone list
evalstone run nightly                    # table + evalstone-report.json
evalstone gate nightly                   # exit 1 when the gate fails (CI)
```

Judges and prompt targets need a provider key in the environment
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, or any
OpenAI-compatible base URL such as OpenRouter or Ollama via `providers:`).
Without one, judge results are **errors, never passes**, and the gate fails.

## Concepts

`Sample` → `Dataset` (content-hashed, so every run pins an exact version) ·
`Check` → `Score` (0..1 + pass/fail + reason; an error is never a pass) ·
`Suite` → `Run` → `Gate`. See the docs for the full vocabulary.
