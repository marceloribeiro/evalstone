<p align="center"><strong>Evalstone</strong></p>

**Evalstone is the plug-and-play evals layer for any LLM-based project: a Python library, a learning center, a check center, an API and an MCP server. First it teaches you what evals are. Then it runs them for you, in CI and in production.**

[![Site CI](https://github.com/marceloribeiro/evalstone/actions/workflows/site.yml/badge.svg)](https://github.com/marceloribeiro/evalstone/actions/workflows/site.yml)
[![Lib CI](https://github.com/marceloribeiro/evalstone/actions/workflows/lib.yml/badge.svg)](https://github.com/marceloribeiro/evalstone/actions/workflows/lib.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Website + docs:** [evalstone.com](https://evalstone.com) · **Learn evals:** [evalstone.com/docs/learn](https://evalstone.com/docs/learn)

> **Status:** the site and the learning center are live. The library's first
> release (0.1.0) is complete in the repo and awaiting its PyPI publish; the
> integrations and the center follow. See the [roadmap](docs/ROADMAP.md).

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
| [`python/evalstone/`](python/evalstone) | Library · CLI (MCP server + pytest plugin in Phase 2) | Python 3.12+ · pydantic · httpx | **0.1.0 candidate** (PyPI publish pending) |
| `python/evalstone-api/` | The center API (sole database owner) | FastAPI · SQLAlchemy 2 · PostgreSQL 16 + pgvector · Redis · Celery | planned |
| `javascript/evalstone-web/` | The center web app | Next.js 16 · React 19 · Tailwind 4 · shadcn | planned |
| [`docs/`](docs) | Architecture, roadmap, decisions | Markdown | — |
| `samples/` | Runnable examples | — | with the library |

## Development

| Package | Commands |
| --- | --- |
| Site | `cd javascript/evalstone-site && just install && just check && just test` |
| Library | `cd python/evalstone && just install && just check` |

See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions.

## License

[MIT](LICENSE). Security policy: [SECURITY.md](SECURITY.md). Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
