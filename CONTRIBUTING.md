# Contributing to Evalstone

Thanks for helping. This file is short on purpose; the longer design notes
live under [`docs/`](docs).

## Ground rules

- **Conventional Commits**, scoped by package:
  `feat(lib): …`, `fix(api): …`, `feat(web): …`, `docs(site): …`, `ci: …`,
  `chore: …`. One logical change per commit.
- **The commit body says what you observed**, not what you intended. If you
  ran it, paste the command and the relevant output. If you did not run it,
  say "built, not run". A commit message never claims more than its diff
  contains.
- **Tests travel with the change.** Services and routes in the API get tests;
  every user-visible feature in a Next.js app gets a Playwright spec.
- **CI must be green** before a pull request is merged. Pull requests are
  squash-merged to `main`.

## Repository layout

| Path | What | Stack |
| --- | --- | --- |
| `python/evalstone` | Library · CLI · MCP server · pytest plugin | Python 3.13 |
| `python/evalstone-api` | The center (control plane, sole database owner) | FastAPI · SQLAlchemy 2 · PostgreSQL 16 + pgvector · Redis · Celery |
| `javascript/evalstone-web` | The center web app | Next.js 16 · React 19 · Tailwind 4 · shadcn |
| `javascript/evalstone-site` | evalstone.com: landing + learning docs | Next.js 16 · Fumadocs |
| `samples/` | Runnable examples | — |
| `docs/` | Architecture, roadmap, decisions | Markdown |

## Local development

Each package has its own `README.md` and a `justfile` with the standard
recipes (`just install`, `just up`, `just check`, `just test`, …).
PostgreSQL and Redis are expected to run natively on your machine; the
`docker-compose.yml` in the repo root (when it lands) is for people trying the
center, not for contributors' day-to-day work.

## Pull requests

Use the template. The **"How I verified"** section is mandatory: what you
ran, what you saw.
