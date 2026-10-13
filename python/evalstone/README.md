# evalstone

The plug-and-play evals layer for LLM-based projects, as a Python library.

> **Status:** in development, not yet on PyPI. Design: [evalstone.com/docs/evalstone/library](https://evalstone.com/docs/evalstone/library).

The library **computes**; it owns no database. A run lives in memory, prints a
table and writes a JSON report. Persistence happens through the Evalstone
center (PostgreSQL) when one is configured.

## Develop

```bash
just install     # venv + editable install with dev extras
just check       # ruff + pytest
just console     # REPL with `es` loaded
```

## Concepts

`Sample` → `Dataset` (content-hashed, so every run pins an exact version) ·
`Check` → `Score` (0..1 + pass/fail + reason; an error is never a pass) ·
`Suite` → `Run` → `Gate`. See the docs for the full vocabulary.
