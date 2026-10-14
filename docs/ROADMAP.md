# Roadmap

Engineering-focused snapshot. Not a product commitment.

## Built

- **Site + learning center** (`javascript/evalstone-site`): landing page and the
  "Evals 101" course on evalstone.com.
- **Library** (`python/evalstone`): datasets, deterministic / judge / RAG /
  safety / pairwise / trajectory checks, targets, suites, runs, gates, CLI,
  provider adapters, `samples/rag-bot`. PRs #1–#7. **On PyPI**: 0.1.0 and 0.1.1
  (2026-10-13), **0.2.0 (2026-10-14)** with the `center:` attach — judges run through
  the center's model proxy, verdicts are cached there, labels are looked up there,
  runs are pushed there.
- **Integrations** — MCP server, pytest plugin and terminal labeling ship with
  the library (PRs #8, #9, #11); the GitHub Action is hosted in the repository
  (PR #10; tags: `action-v0` floating, `action-v0.1.0` pinned). Site guides + reference: PR #12.
- **Center API** (`python/evalstone-api`, PRs #23–#40, 2026-10-13): organizations,
  members and invitations, projects and ingest keys; providers with encrypted keys and
  per-project judge settings; a synchronous model-call proxy; datasets with immutable
  content-hashed versions; runs, results, baselines and diffs; judge cache and labels;
  the check catalog (built-ins introspected from the library, org checks versioned);
  labeling queues (grade / compare / verify); judge calibration (Celery); trace ingest,
  monitors on the beat, alerts with webhooks; WebSocket live updates on one-time tickets;
  `docker-compose.yml` + `QUICK_START.md` for self-hosters; every Redis key namespaced
  (`REDIS_KEY_PREFIX`, PR #50).
- **Center web** (`javascript/evalstone-web`, PRs #41–#49, 2026-10-13/14): project
  home with the live feed, runs with per-check / results / diff, datasets with version
  diff and tagging, the keyboard-driven labeler, judges (providers, settings, calibration,
  promote), monitors + alerts + traces, members and invitations, project settings, the
  check catalog editor. 34 Playwright specs.
- **Hosted center** — `https://api.evalstone.com` + `https://app.evalstone.com` on the
  operator's server since 2026-10-14, with a demo organization built from `samples/rag-bot`
  (`python/evalstone-api/scripts/seed_demo.py`); nightly database backups.

## Next (in order)

1. **A viewer role** — the public demo signs in as a member today (it can read, label and
   push, not delete); a role below member that only reads is the right guard.
2. **Judged demo content** — judged runs, a calibration and a promoted judge in the demo
   organization (needs a provider key in the hosted center).
3. **Email alerts** (Postmark) next to the webhook — deferred from the monitoring slice.
4. **Harvest from traces** into a dataset version with embedding dedup (the pgvector column
   exists; needs an embedding provider).
5. **Org checks by reference** — the library pulling `checks:` from the center at run time
   (today: paste the YAML block the catalog page shows).
6. **Bulk judge-cache warming** and threshold-based judge promotion.

## Deferred (tracked, honored)

| Item | Why | Revisit |
| --- | --- | --- |
| TypeScript library | HTTP API + MCP cover non-Python callers in v1 | after 0.2.0 adoption |
| Fine-tuning execution | the training loop tracks iterations; it does not train weights | — |
