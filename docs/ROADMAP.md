# Roadmap

Engineering-focused snapshot. Not a product commitment.

## Built

- **Site + learning center** (`javascript/evalstone-site`): landing page and the
  "Evals 101" course on evalstone.com.

## Next (in order)

1. **Library core** — datasets, deterministic checks, targets, suites, runs,
   gates; judge adapters (OpenAI-compatible, Anthropic, Gemini); RAG, safety,
   pairwise and agent-trajectory checks; CLI; PyPI `0.1.0`.
2. **Integrations** — MCP server, pytest plugin, GitHub Action, terminal labeling.
3. **Center API** — orgs, projects, datasets + versions (pgvector dedup), run
   history, catalog, labeling queues, judge calibration, trace ingest + monitors +
   alerts, WebSocket; `docker-compose.yml` for self-hosters.
4. **Center web** — runs, datasets, labeling, judges, monitors.
5. **Hosted demo** — api.evalstone.com + app.evalstone.com.

## Deferred (tracked, honored)

| Item | Why | Revisit |
| --- | --- | --- |
| TypeScript library | HTTP API + MCP cover non-Python callers in v1 | after 0.2.0 |
| Fine-tuning execution | the training loop tracks iterations; it does not train weights | — |
