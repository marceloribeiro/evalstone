#!/bin/sh
# Waits for Postgres, migrates (api only), then runs the requested process.
set -e

wait_for_db() {
  # The app's own Settings/engine: the DSN is percent-encoded (any DB_PASS works) and the
  # secrets validator fires here, before a minute of waiting, if .env is incomplete.
  python - <<'PY'
import sys, time
from sqlalchemy import text
from app.db import engine  # connect_timeout=2 is set there
deadline = time.monotonic() + 120
while True:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("postgres: ready"); sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        left = deadline - time.monotonic()
        if left <= 0:
            sys.exit(f"postgres: not reachable after 120s ({type(exc).__name__})")
        print(f"postgres: waiting ({type(exc).__name__}, {int(left)}s left)"); time.sleep(2)
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
