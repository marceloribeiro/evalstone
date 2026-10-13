# evalstone-api

The Evalstone **center API**: FastAPI, the sole owner of PostgreSQL (ADR-001).
Organizations, projects, provider settings, datasets, runs, labels, judge
calibration and monitoring land here slice by slice (`docs/ROADMAP.md`).

## Local development

PostgreSQL 16 and Redis run natively on your machine (no containers).

```bash
cp .env.example .env         # DB_USER = your OS user; pick a free Redis index
just install                 # python3.13 -m venv venv + requirements-dev.txt (runtime + tooling)
just services-check          # postgres + redis up?
just db-create-all           # evalstone_api_development + evalstone_api_test
just db-migrate-all          # alembic upgrade head on both
just up                      # http://localhost:8181/health · /ready · /docs (basic auth)
just workers                 # celery worker  (CELERY_POOL=solo on macOS)
just beat                    # celery beat    (heartbeat every 5 min)
just check                   # ruff + pytest (tests hit evalstone_api_test)
just console                 # IPython with `db`, models and `tasks` loaded
```

`just test` runs against the `_test` database and truncates every table after
each test; it never touches the development database.

## Layout

```
app/
  main.py        FastAPI app, CORS, basic-auth /docs, DomainError → HTTP
  config.py      pydantic-settings (.env)
  db.py          engine + SessionLocal + get_db
  errors.py      NotFound / Conflict / Forbidden / Unauthorized / Invalid
  models/        SQLAlchemy 2 models (TimestampedModel: uuid pk, created/updated/deleted_at)
  routers/       HTTP only — call services, never the database
  services/      business logic — own the models
  schemas/       pydantic request/response models
  deps.py        current user (JWT), org membership + role gate, project context, ingest key
  security.py    bcrypt passwords, HS256 JWTs, ingest-key generation/hashing
  worker.py      Celery app (+ beat schedule)
  tasks.py       Celery tasks
  support/systemd/  evalstone-api · -celery · -celery-beat units
alembic/         migrations named YYYYMMDD_HHmmss_<slug>.py
nginx/           api.evalstone.com vhost (http, then https)
scripts/console.py
tests/
```

## Endpoints (so far)

| Area | Routes | Who |
| --- | --- | --- |
| Auth | `POST /auth/register` · `POST /auth/login` · `GET /me` | anyone / bearer JWT |
| Organizations | `GET,POST /organizations` · `GET,PATCH,DELETE /organizations/{id}` | member · admin · owner |
| Members | `GET /organizations/{id}/members` · `PATCH,DELETE …/members/{member_id}` | admin+; ownership changes need an owner; the last owner stays |
| Invitations | `GET,POST /organizations/{id}/invitations` · `DELETE …/invitations/{inv_id}` | admin+. An existing user joins at once; a new address joins on register |
| Projects | `GET,POST /organizations/{id}/projects` · `GET,PATCH,DELETE /projects/{id}` | member reads, admin+ writes |
| Ingest keys | `GET,POST /projects/{id}/ingest-keys` · `DELETE …/ingest-keys/{key_id}` (revoke) | admin+. The `es_…` secret is returned once; only its sha256 is stored |
| Ingest | `GET /ingest/whoami` | `Authorization: Bearer es_…` |
| Health | `GET /health` · `GET /ready` · `GET /docs` (basic auth) | — |

Outsiders get `404`, not `403`, for organizations and projects they do not belong to.

## Deploy

`just deploy` clones the monorepo on the server named in `deploy.json`,
installs this package under `/home/ubuntu/evalstone-api/releases/<ts>`,
migrates, repoints `current` and restarts the three units. First time:
`just setup-systemd`, `just setup-nginx-http`, then TLS and
`just setup-nginx-https`. The operator supplies `.env.production`.
