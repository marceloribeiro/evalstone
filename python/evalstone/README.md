# evalstone

The plug-and-play evals layer for LLM-based projects, as a Python library.

> **Status:** 0.1.0. Docs: [evalstone.com/docs/evalstone/library](https://evalstone.com/docs/evalstone/library).
> Source and samples: [github.com/marceloribeiro/evalstone](https://github.com/marceloribeiro/evalstone).

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
pip install evalstone
evalstone init my-evals                  # evalstone.yaml + a golden set + recorded outputs + a check
cd my-evals
evalstone run nightly                    # table + evalstone-report.json
evalstone gate nightly                   # exit 1 when the gate fails (CI)
```

A fuller example — a small retrieval bot with a gated suite — lives in the
repository under `samples/rag-bot` (`git clone` it, `pip install -e
python/evalstone`, then `evalstone run nightly` inside the sample).

Judges and prompt targets need a provider key in the environment
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, or any
OpenAI-compatible base URL such as OpenRouter or Ollama via `providers:`).
Without one, judge results are **errors, never passes**, and the gate fails.

## Concepts

`Sample` → `Dataset` (content-hashed, so every run pins an exact version) ·
`Check` → `Score` (0..1 + pass/fail + reason; an error is never a pass) ·
`Suite` → `Run` → `Gate`. See the docs for the full vocabulary.
