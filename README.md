<p align="center"><strong>Evalstone</strong></p>

**Open-source evals for LLM apps — and a course on how to do them.** Write datasets, checks
and gates in plain Python, run them in CI, and keep a shared golden set, a labeling queue
and an LLM judge you have measured against people in one center.

[![Site CI](https://github.com/marceloribeiro/evalstone/actions/workflows/site.yml/badge.svg)](https://github.com/marceloribeiro/evalstone/actions/workflows/site.yml)
[![Lib CI](https://github.com/marceloribeiro/evalstone/actions/workflows/lib.yml/badge.svg)](https://github.com/marceloribeiro/evalstone/actions/workflows/lib.yml)
[![PyPI](https://img.shields.io/pypi/v/evalstone)](https://pypi.org/project/evalstone/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

```bash
pip install evalstone
evalstone init          # a starter evalstone.yaml, a golden set, recorded outputs, a custom check
evalstone run nightly   # the results table + a JSON report
evalstone gate nightly  # exits 1 when the gate fails: that is your CI step
```

**Learn evals:** [Evals 101](https://evalstone.com/docs/learn) · **Docs:** [evalstone.com](https://evalstone.com)
· **Try the center:** [app.evalstone.com](https://app.evalstone.com) (the demo login is on the
[Center page](https://evalstone.com/docs/evalstone/center))

| A run: per-check results, the gate, the judge's reasons | Labeling: grade outputs from the keyboard | Calibration: how far to trust a judge, then Promote it |
| --- | --- | --- |
| ![A judged run in the center](docs/img/run.png) | ![The labeler](docs/img/labeler.png) | ![Judges and a calibration](docs/img/calibration.png) |

> **Status:** the library is on PyPI (CLI, MCP server, pytest plugin, terminal labeling), the
> GitHub Action is `marceloribeiro/evalstone/action@action-v0`, and the center is live at
> [app.evalstone.com](https://app.evalstone.com) or self-hosted with `docker compose`
> ([`QUICK_START.md`](QUICK_START.md)). See the [roadmap](docs/ROADMAP.md).

## What it is

Shipping an LLM feature by trying three prompts and calling it fine works
until it doesn't. Evalstone turns the practice in [Evals 101](https://evalstone.com/docs/learn)
into software you add to an existing project without a rewrite:

- **Library** (`pip install evalstone`) — datasets, checks, suites, runs and
  gates as plain Python; deterministic checks, LLM judges, RAG, safety,
  pairwise and agent-trajectory checks built in; a CLI.
- **Training center** — versioned golden sets harvested from real traffic, a
  human labeling queue, judge calibration against human labels.
- **Check center** — run history with baselines and diffs, a catalog of
  reusable checks, production monitors and alerts.
- **CI gate** — GitHub Action + pytest plugin.
- **API** — everything the center does, as REST with OpenAPI docs.
- **MCP server** — run suites and judge outputs from Claude Code, Cursor or any
  MCP client.

One design rule: **the library computes, the center stores.** The library has
no database; the center API is the sole owner of PostgreSQL.

## Repository layout

| Path | What | Stack | Status |
| --- | --- | --- | --- |
| [`javascript/evalstone-site/`](javascript/evalstone-site) | evalstone.com — landing + learning docs | Next.js 16 · React 19 · Tailwind 4 · Fumadocs | **live** |
| [`python/evalstone/`](python/evalstone) | Library · CLI · MCP server · pytest plugin · labeling | Python 3.12+ · pydantic · httpx | **on PyPI** |
| [`python/evalstone-api/`](python/evalstone-api) | The center API (sole database owner) | FastAPI · SQLAlchemy 2 · PostgreSQL 16 + pgvector · Redis · Celery | **live** at [api.evalstone.com](https://api.evalstone.com) · self-host: [`QUICK_START.md`](QUICK_START.md) |
| [`javascript/evalstone-web/`](javascript/evalstone-web) | The center web app | Next.js 16 · React 19 · Tailwind 4 · shadcn | **live** at [app.evalstone.com](https://app.evalstone.com) |
| [`action/`](action) | GitHub Action: run a suite on PRs, comment, fail on the gate | composite action | **live** (dogfooded by `evals.yml`) |
| [`docs/`](docs) | Architecture, roadmap, decisions | Markdown | — |
| [`samples/`](samples) | Runnable examples (`rag-bot`: deterministic, CI and judged suites) | — | with the library |

## Development

| Package | Commands |
| --- | --- |
| Site | `cd javascript/evalstone-site && just install && just check && just test` |
| Library | `cd python/evalstone && just install && just check` |
| Center API | `cd python/evalstone-api && just install && just up` (Postgres + Redis running natively; Celery: `just workers`, `just beat`; `just check` = lint + tests) |
| Center web | `cd javascript/evalstone-web && just install && just up` (dev server on :8182, needs the API's `just up`; `just check` = lint + types, `just test` = Playwright) |

See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions.

## License

[MIT](LICENSE). Security policy: [SECURITY.md](SECURITY.md). Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
