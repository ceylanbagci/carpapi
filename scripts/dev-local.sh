#!/usr/bin/env bash
#
# CarPapi — start a full local dev stack.
#
# Two long-running processes:
#   1. Django on http://localhost:8000  (reads local Postgres :5433 +
#      uses console email backend so password-reset emails print
#      to the terminal instead of needing real SMTP)
#   2. Vite on http://localhost:5173    (proxies /api → :8000 per
#      vite.config.js, so the SPA + API are same-origin in dev and
#      cookies/CORS Just Work)
#
# Usage:
#   ./scripts/dev-local.sh           # start both (foreground)
#   ./scripts/dev-local.sh backend   # start only Django
#   ./scripts/dev-local.sh frontend  # start only Vite
#   Ctrl-C kills both.
#
# Prereqs (all already installed if you've run the deploy scripts):
#   - Local Postgres 17.9 on :5433 with role/db `carpapi/carpapi`
#   - .venv/ with backend deps (created by deploy/aws_bootstrap or
#     `python -m venv .venv && .venv/bin/pip install -r web/backend/requirements.txt`)
#   - web/frontend/node_modules (`cd web/frontend && npm i`)
#
# This script does NOT touch RDS, App Runner, CloudFront, S3, or any
# AWS resource. It's purely local.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WHAT="${1:-both}"

# Shared env for the Django process.
export DJANGO_SETTINGS_MODULE=carpapi_web.settings
export DJANGO_DEBUG=true
export DJANGO_SECRET_KEY=dev-only-not-for-production-replace-me-9f80136
export DJANGO_ALLOWED_HOSTS='localhost,127.0.0.1,0.0.0.0,*'
export CARPAPI_DB_HOST=localhost
export CARPAPI_DB_PORT=5433
export CARPAPI_DB_NAME=carpapi
export CARPAPI_DB_USER=carpapi
export CARPAPI_DB_PASSWORD=carpapi
# Console email backend — password-reset emails land in the Django
# stdout so the demo flow is testable end-to-end without SMTP.
export DJANGO_EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
# In dev, /api/chat/ doesn't require auth (settings.DEBUG=true short-
# circuits the gate). The frontend will still try to send JWT tokens;
# the backend just accepts the call when DEBUG is on.

# Pick a Python interpreter — prefer the venv if it exists.
PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"

print_section() {
  printf '\n\033[1;36m── %s ──\033[0m\n' "$*"
}

start_backend() {
  print_section "Backend (Django)  http://localhost:8000"
  cd "$ROOT/web/backend"
  # Run any pending migrations once before runserver (cheap; idempotent).
  "$ROOT/$PY" manage.py migrate --noinput >/dev/null
  echo "  migrations: up-to-date"
  # ensure_superuser is the same idempotent command used in production.
  # Picks up DJANGO_SUPERUSER_{EMAIL,PASSWORD,FULL_NAME} if set; quietly
  # no-ops otherwise.
  "$ROOT/$PY" manage.py ensure_superuser >/dev/null 2>&1 || true
  exec "$ROOT/$PY" manage.py runserver 0.0.0.0:8000
}

start_frontend() {
  print_section "Frontend (Vite)   http://localhost:5173"
  cd "$ROOT/web/frontend"
  # VITE_API_BASE empty → defaults to /api → vite.config.js proxies
  # /api → http://localhost:8000. Same-origin in dev = no CORS pain.
  unset VITE_API_BASE
  export VITE_API_TARGET=http://localhost:8000
  exec npm run dev
}

case "$WHAT" in
  backend)  start_backend ;;
  frontend) start_frontend ;;
  both)
    # Run backend in background, frontend in foreground. Trap Ctrl-C
    # so killing the script kills the backend too.
    (start_backend) &
    BACKEND_PID=$!
    trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT INT TERM
    # Give the backend a moment to bind :8000 before vite probes it.
    sleep 2
    start_frontend
    ;;
  *)
    echo "Usage: $0 [both|backend|frontend]" >&2
    exit 1
    ;;
esac
