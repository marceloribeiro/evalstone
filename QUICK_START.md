# Quick start — run the Evalstone center with Docker

The hosted center is at **https://app.evalstone.com** (API: `https://api.evalstone.com`) — sign in
with the demo account on the [Center page](https://evalstone.com/docs/evalstone/center) to look
around before running your own.

For trying the center on one machine. Contributors run Postgres and Redis natively instead
(see `python/evalstone-api/README.md`).

## 1. Start it

```bash
git clone https://github.com/marceloribeiro/evalstone.git && cd evalstone
cp env.docker.example .env
# fill in DB_PASS, JWT_SECRET, PROVIDER_CREDS_KEY, DOCS_PASSWORD (generators are in the file)
docker compose up -d --build
docker compose ps          # api / worker / beat / postgres / redis — api becomes "healthy"
curl -s localhost:8181/ready
```

The first start builds the API image and migrates the database (Alembic, including the
pgvector extension). API docs: http://localhost:8181/docs (basic auth: `DOCS_USERNAME` /
`DOCS_PASSWORD`).

## 2. Create your account, organization and project

```bash
API=http://localhost:8181
TOKEN=$(curl -s -X POST $API/auth/register -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"choose-a-password"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
ORG=$(curl -s -X POST $API/organizations -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"name":"My team"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
PROJECT=$(curl -s -X POST $API/organizations/$ORG/projects -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"name":"my-bot"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
KEY=$(curl -s -X POST $API/projects/$PROJECT/ingest-keys -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"name":"laptop"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["key"])')
echo "project $PROJECT  ingest key $KEY"
```

## 3. Add a provider and pick the judge model (the keys stay in the center)

```bash
curl -s -X POST $API/organizations/$ORG/providers -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"name":"anthropic","adapter":"anthropic","api_key":"sk-ant-…"}'
curl -s -X PUT $API/projects/$PROJECT/judge-settings -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"default_model":"anthropic/claude-sonnet-5-5"}'
```

## 4. Attach a project and run

In your project's `evalstone.yaml` (no `providers:` needed — judges go through the center):

```yaml
center:
  url: http://localhost:8181
  project: <PROJECT>
```

```bash
pip install 'evalstone>=0.2.0'      # the `center:` attach shipped in 0.2.0
EVALSTONE_API_KEY=$KEY evalstone run <suite>     # judged through the center; the run is stored
```

Runs, datasets, labels, judge cache, calibrations, monitors and alerts all live in the center
now. The web app (`javascript/evalstone-web`, a standalone Next.js build) sits on top of the same
API: set its `NEXT_PUBLIC_API_URL` to the API and serve it next to it.

## Operating it

- `docker compose logs -f api worker beat`
- Data lives in the `postgres-data` volume; `docker compose down -v` deletes it.
- Upgrading: `git pull && docker compose up -d --build` (the API migrates on start).
- Behind a reverse proxy, forward `/ws/` as a WebSocket upgrade (see `python/evalstone-api/nginx/`).
