#!/usr/bin/env bash
# Start the FastAPI backend on a fresh, disposable SQLite database for the GUI tests.
# Used by playwright.config.ts; can also be run by hand from the repo root.
set -euo pipefail

cd "$(dirname "$0")/../../backend"
PY="${E2E_PYTHON:-.venv/bin/python}"

export DATABASE_URL="sqlite:///./e2e.db"
export ENVIRONMENT=development
export EMAIL_PROVIDER=mock
export ALLOW_DEMO_SEEDING=false
export CORS_ORIGINS="http://127.0.0.1:${E2E_WEB_PORT:-5180}"

rm -f e2e.db
"$PY" -m alembic upgrade head
"$PY" -m app.scripts.seed_departments
PYTHONPATH=. "$PY" ../e2e/seed_e2e.py
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "${E2E_API_PORT:-8010}"
