# evalstone-api

The Evalstone **center API**: FastAPI, the sole owner of PostgreSQL (ADR-001).
Organizations, projects, provider settings, datasets, runs, labels, judge
calibration and monitoring land here slice by slice (`docs/ROADMAP.md`).

## Local development

PostgreSQL 16 (with the **pgvector** extension: `brew install pgvector`) and Redis run
natively on your machine (no containers). The first migration runs
`CREATE EXTENSION IF NOT EXISTS vector`, which needs a superuser role once per database;
the Homebrew OS-user role is one, on a server the operator runs it before the first migrate.

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
  crypto.py      Fernet encrypt/decrypt for provider keys (PROVIDER_CREDS_KEY — stable forever)
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
| Providers | `GET,POST /organizations/{id}/providers` · `GET,PATCH,DELETE …/providers/{pid}` · `POST …/providers/{pid}/test` | members read (masked), admin+ write. Keys are Fernet-encrypted with `PROVIDER_CREDS_KEY`, write-only (`has_api_key` + `key_last4`), decrypted only in-process to make a call. `base_url` passes an SSRF guard (`PROVIDER_ALLOW_PRIVATE_URLS` for a local gateway) |
| Judge settings | `GET,PUT /projects/{id}/judge-settings` | default `<provider>/<model>` + per-check overrides; providers must exist in the org |
| Datasets | `GET,POST /projects/{id}/datasets` · `GET,PATCH,DELETE …/datasets/{did}` · `GET,POST …/datasets/{did}/versions` · `GET …/versions/{n}` · `GET …/versions/{n}/samples?offset&limit` | members or the project's `es_…` key read and push; admin+ edits/deletes. A version is an immutable snapshot whose `content_hash` equals the library's `Dataset.content_hash`; pushing unchanged content returns the latest version (200). Samples are stored once per project by content |
| Runs | `POST /projects/{id}/runs` (body = `evalstone-report.json`) · `GET …/runs?suite&baseline&offset&limit` · `GET …/runs/{rid}` · `GET …/runs/{rid}/results?check_key&failed_only` · `GET …/runs/{rid}/report` · `GET …/runs/{rid}/compare/{other}` · `PUT …/runs/{rid}/baseline` | members or the project's `es_…` key push and read; members set the baseline. A report is stored once per client run id (re-push → 200). The dataset version is linked by content hash when the center has it. `report` returns the library's JSON back; `compare` is the library's `compare()` over the stored rows; one baseline per suite |
| Judge cache | `GET,PUT /projects/{id}/judge-cache/{key}` · `POST …/judge-cache/lookup` | members or the `es_…` key. The library's `ScoreCache` over HTTP: `key` = the library's `cache_key` (64-hex), value = its `Score` JSON. A verdict paid for on one machine serves every later run |
| Labels | `GET,POST /projects/{id}/labels` · `GET …/labels/lookup?sample_key&output_hash&check` · `GET …/labels/export` (JSONL) · `DELETE …/labels/{lid}` | members or the key push/read; admin+ deletes. The library's `Label` shape (a `labels.jsonl` line); later wins per (sample, output hash, check); `export` is a drop-in `labels.jsonl` |
| Model proxy | `POST /projects/{id}/model/complete` · `GET …/model/calls` | members or the `es_…` key. The library's `Providers.complete()` run inside the center: the body is the canonical request (system, messages, max_tokens) plus `model` (`<provider>/<model>`) **or** `check_key` (resolved from the project's judge settings); the org's key is decrypted in-process and never returned; the response is the library's `ChatResponse`. 502 when the provider fails; every call (ok or failed) is metered under `model/calls` with tokens, cost and the caller |
| Check catalog | `GET /catalog/checks` · `GET,POST /organizations/{id}/checks` · `GET …/checks/yaml` · `GET,PUT,DELETE …/checks/{cid}` · `GET …/checks/{cid}/versions[/{n}]` | built-ins = the installed library's `FACTORIES` (type, kind, params, summary); org checks are a type + params validated against the factory signature (no files/code params), versioned on every content change; `yaml` returns the org's `checks:` block for an evalstone.yaml |
| Labeling | `GET,POST /projects/{id}/label-queues` · `GET,PATCH …/label-queues/{qid}` · `GET …/progress` · `POST …/assign` · `GET …/tasks?status&assignee=me` · `POST …/next` · `POST …/tasks/{tid}/answer` · `POST …/tasks/{tid}/skip` | members label; admin+ creates/assigns/closes. A queue materialises one task per sample from a run (`grade`), two runs (`compare` A/B) or a dataset version (`verify`); `next` claims atomically (`SKIP LOCKED`); an answer becomes a label keyed by sample + output hash — exactly what the `human` check and calibration read |
| Health | `GET /health` · `GET /ready` · `GET /docs` (basic auth) | — |

Outsiders get `404`, not `403`, for organizations and projects they do not belong to.

## Deploy

`just deploy` clones the monorepo on the server named in `deploy.json`,
installs this package under `/home/ubuntu/evalstone-api/releases/<ts>`,
migrates, repoints `current` and restarts the three units. First time:
`just setup-systemd`, `just setup-nginx-http`, then TLS and
`just setup-nginx-https`. The operator supplies `.env.production`.
