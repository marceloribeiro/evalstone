# Roadmap

Engineering-focused snapshot. Not a product commitment.

## Built

- **Site + learning center** (`javascript/evalstone-site`): landing page and the
  "Evals 101" course on evalstone.com.
- **Library 0.1.0** (`python/evalstone`): datasets, deterministic / judge / RAG /
  safety / pairwise / trajectory checks, targets, suites, runs, gates, CLI,
  provider adapters, `samples/rag-bot`. Shipped as PRs #1–#7. **On PyPI as
  0.1.0** (2026-10-13, tag `lib-v0.1.0`, trusted publisher via
  `.github/workflows/release.yml`).
- **Integrations** — MCP server, pytest plugin and terminal labeling ship with
  the library (PRs #8, #9, #11); the GitHub Action is hosted in the repository
  (PR #10, tag `action-v0.1.0`). Site guides + reference: PR #12.

## Next (in order)

1. **Center API** — orgs, projects, datasets + versions (pgvector dedup), run
   history, catalog, labeling queues, judge calibration, trace ingest + monitors +
   alerts, WebSocket; `docker-compose.yml` for self-hosters.
2. **Center web** — runs, datasets, labeling, judges, monitors.
3. **Hosted demo** — api.evalstone.com + app.evalstone.com.

## Deferred (tracked, honored)

| Item | Why | Revisit |
| --- | --- | --- |
| TypeScript library | HTTP API + MCP cover non-Python callers in v1 | after 0.2.0 |
| Fine-tuning execution | the training loop tracks iterations; it does not train weights | — |
