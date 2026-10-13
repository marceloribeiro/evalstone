#!/bin/sh
# Waits for Postgres, migrates (api only), then runs the requested process.
set -e

wait_for_db() {
  python - <<'PY'
import os, sys, time
import psycopg
url = f"postgresql://{os.environ['DB_USER']}:{os.environ.get('DB_PASS','')}@{os.environ['DB_HOST']}:{os.environ.get('DB_PORT','5432')}/{os.environ['DB_NAME']}"
for attempt in range(60):
    try:
        psycopg.connect(url, connect_timeout=2).close()
        print("postgres: ready"); sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"postgres: waiting ({exc.__class__.__name__})"); time.sleep(2)
sys.exit("postgres: not reachable after 120s")
PY
}

case "${1:-api}" in
  api)
    wait_for_db
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port 8181 ;;
  worker)
    wait_for_db
    exec celery -A app.worker.celery_app worker --loglevel=INFO --pool=prefork --concurrency="${CELERY_CONCURRENCY:-2}" ;;
  beat)
    wait_for_db
    exec celery -A app.worker.celery_app beat --loglevel=INFO --schedule=/tmp/celerybeat-schedule ;;
  *)
    exec "$@" ;;
esac
