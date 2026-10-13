# Architecture

> Status: the design is settled; the site is the first piece shipped. Package
> directories appear as they land — see [ROADMAP.md](ROADMAP.md).

Evalstone has three runtime pieces and one site.

```
your code ──(pip install evalstone)──► library ──(HTTP, optional)──► center API ──► PostgreSQL
                                          │                              ▲   │
   CLI · pytest plugin · MCP server ──────┘                              │   └─► Redis (live updates)
                                                                         │        Celery (jobs)
                                              center web (Next.js) ──────┘
```

## Library (`python/evalstone`)

Pure compute. Loads datasets, runs checks over a target's outputs, prints a
results table, writes a JSON report, and enforces a gate (exit code). It owns
**no database**. With `center.url` configured it persists runs, results, labels
and judge-cache entries through the center API.

Also ships the CLI (`evalstone`), the MCP server (`evalstone mcp`) and the
pytest plugin — same package, same concepts.

## Center API (`python/evalstone-api`)

FastAPI. **The sole owner of PostgreSQL.** Organizations, projects, datasets
with immutable versions, the check catalog, runs and results, labeling queues,
judge versions and calibration jobs, production trace ingest with monitors and
alerts. Routers call services; services own the models. Long work runs on
Celery; live updates go over Redis pub/sub to a WebSocket.

## Center web (`javascript/evalstone-web`)

Next.js. Dashboards, dataset browser, labeling queue, run diffs, judges,
monitors. Reads the API over REST + WebSocket.

## Site (`javascript/evalstone-site`)

evalstone.com. Landing page plus the learning docs (Fumadocs). Static-ish,
self-hosted with the same deploy kit as every other piece.

## Guarantees

- A judge error is never a pass.
- Runs pin an immutable dataset version and a git SHA, so any two runs compare.
- Provider API keys are read from the environment and never stored.
