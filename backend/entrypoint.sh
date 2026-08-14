#!/bin/sh
# Container entrypoint. Usage: entrypoint.sh [api|worker|beat|migrate|seed|shell]
set -eu

MODE="${1:-api}"

wait_for_db() {
  echo "[entrypoint] waiting for database..."
  python - <<'PY'
import sys, time
from sqlalchemy import create_engine, text
from app.core.config import settings

url = settings.sqlalchemy_database_uri
for attempt in range(60):
    try:
        create_engine(url, pool_pre_ping=True).connect().execute(text("SELECT 1"))
        print("[entrypoint] database is ready")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"[entrypoint] db not ready ({attempt + 1}/60): {exc.__class__.__name__}")
        time.sleep(2)
print("[entrypoint] database never became ready")
sys.exit(1)
PY
}

case "$MODE" in
  api)
    wait_for_db
    echo "[entrypoint] running migrations"
    alembic upgrade head
    echo "[entrypoint] seeding baseline data"
    python -m scripts.seed --skills --users
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
    ;;
  worker)
    wait_for_db
    exec celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --concurrency="${CELERY_CONCURRENCY:-2}"
    ;;
  beat)
    exec celery -A app.workers.celery_app.celery_app beat --loglevel=INFO
    ;;
  migrate)
    wait_for_db
    exec alembic upgrade head
    ;;
  seed)
    wait_for_db
    exec python -m scripts.seed --skills --users --demo
    ;;
  shell)
    exec /bin/bash
    ;;
  *)
    exec "$@"
    ;;
esac
