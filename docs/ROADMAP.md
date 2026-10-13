# Roadmap

Engineering-focused snapshot. Not a product commitment.

## Built

- **Site + learning center** (`javascript/evalstone-site`): landing page and the
  "Evals 101" course on evalstone.com.
- **Library 0.1.0** (`python/evalstone`): datasets, deterministic / judge / RAG /
  safety / pairwise / trajectory checks, targets, suites, runs, gates, CLI,
  provider adapters, `samples/rag-bot`. Shipped as PRs #1–#7. **PyPI publish
  pending** the trusted-publisher setup (`.github/workflows/release.yml`).

## Next (in order)

1. **Integrations** — MCP server, pytest plugin, GitHub Action, terminal labeling.
2. **Center API** — orgs, projects, datasets + versions (pgvector dedup), run
   history, catalog, labeling queues, judge calibration, trace ingest + monitors +
   alerts, WebSocket; `docker-compose.yml` for self-hosters.
3. **Center web** — runs, datasets, labeling, judges, monitors.
4. **Hosted demo** — api.evalstone.com + app.evalstone.com.

## Deferred (tracked, honored)

| Item | Why | Revisit |
| --- | --- | --- |
| TypeScript library | HTTP API + MCP cover non-Python callers in v1 | after 0.2.0 |
| Fine-tuning execution | the training loop tracks iterations; it does not train weights | — |
