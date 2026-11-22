#!/bin/sh
set -e

echo "Applying database migrations..."
alembic upgrade head

if [ "${SEED_ON_START:-false}" = "true" ]; then
  echo "Loading case-study demo data (skipped if data exists)..."
  python -m seed.run
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
