#!/usr/bin/env bash
#
# Local dev runner — boots Django (web/backend) and Vite (web/frontend)
# side by side, with interleaved prefixed logs and Ctrl+C cleanup.
#
# Usage:
#   scripts/dev.sh             # foreground, both servers
#   scripts/dev.sh backend     # backend only
#   scripts/dev.sh frontend    # frontend only
#   scripts/dev.sh check       # don't run anything, just verify the setup
#
# Configure DB connection via web/backend/.env.local (gitignored). See
# web/backend/.env.example for the variable names. If no file exists,
# the defaults inside web/backend/carpapi_web/settings.py win
# (localhost:5433, user/db/password = carpapi).
#
set -euo pipefail

# --------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------- #

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/web/backend"
FRONTEND="$ROOT/web/frontend"
LOGDIR="$ROOT/.logs"
mkdir -p "$LOGDIR"

# Colors — only enabled on a TTY
if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'; C_DIM=$'\033[2m'
  C_BACK=$'\033[36m'  # cyan
  C_FRONT=$'\033[35m' # magenta
  C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'
else
  C_RESET=''; C_DIM=''; C_BACK=''; C_FRONT=''; C_OK=''; C_WARN=''; C_ERR=''
fi

log() { printf "%s\n" "${C_DIM}[dev]${C_RESET} $*"; }
warn() { printf "%s\n" "${C_WARN}[dev]${C_RESET} $*"; }
die() { printf "%s\n" "${C_ERR}[dev]${C_RESET} $*" >&2; exit 1; }

# --------------------------------------------------------------------- #
# Setup checks (auto-install if needed)
# --------------------------------------------------------------------- #

ensure_backend() {
  if [[ ! -d "$BACKEND/.venv" ]]; then
    log "creating venv at web/backend/.venv …"
    python3 -m venv "$BACKEND/.venv"
  fi
  if ! "$BACKEND/.venv/bin/python" -c "import django" 2>/dev/null; then
    log "installing backend requirements …"
    "$BACKEND/.venv/bin/pip" install --quiet --upgrade pip
    "$BACKEND/.venv/bin/pip" install --quiet -r "$BACKEND/requirements.txt"
  fi
}

ensure_frontend() {
  if [[ ! -d "$FRONTEND/node_modules" ]]; then
    log "installing frontend deps (this can take a minute) …"
    ( cd "$FRONTEND" && npm install --silent )
  fi
}

ensure_env() {
  # Source .env.local if the user has one; otherwise the Django defaults apply.
  if [[ -f "$BACKEND/.env.local" ]]; then
    log "sourcing $BACKEND/.env.local"
    set -a
    # shellcheck disable=SC1090
    source "$BACKEND/.env.local"
    set +a
  fi
}

free_port() {
  local port=$1 name=$2
  local pids
  pids=$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    warn "port $port already in use by $name (pid $pids); killing"
    kill $pids 2>/dev/null || true
    sleep 1
  fi
}

# --------------------------------------------------------------------- #
# Start helpers
# --------------------------------------------------------------------- #

# Stream child stdout with a prefix + color, also tee to a log file.
# Args: <prefix> <color> <logfile>
stream() {
  local prefix=$1 color=$2 logfile=$3
  while IFS= read -r line; do
    printf "%s%s%s %s\n" "$color" "[$prefix]" "$C_RESET" "$line"
    printf "%s\n" "$line" >> "$logfile"
  done
}

start_backend() {
  ensure_backend
  free_port 8000 backend
  log "starting Django on http://0.0.0.0:8000"
  ( cd "$BACKEND" && \
      "$BACKEND/.venv/bin/python" manage.py runserver 0.0.0.0:8000 2>&1 \
  ) | stream "back" "$C_BACK" "$LOGDIR/backend.log" &
  BACKEND_PID=$!
}

start_frontend() {
  ensure_frontend
  free_port 5173 frontend
  log "starting Vite on http://0.0.0.0:5173"
  ( cd "$FRONTEND" && npm run dev 2>&1 ) \
    | stream "front" "$C_FRONT" "$LOGDIR/frontend.log" &
  FRONTEND_PID=$!
}

# --------------------------------------------------------------------- #
# Cleanup on Ctrl+C
# --------------------------------------------------------------------- #

cleanup() {
  echo
  log "shutting down …"
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  # Also reap any orphaned children that snuck out from under the pipe
  pkill -P $$ 2>/dev/null || true
  free_port 8000 backend
  free_port 5173 frontend
  log "stopped."
  exit 0
}
trap cleanup INT TERM

# --------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------- #

mode="${1:-both}"

case "$mode" in
  check)
    ensure_backend
    ensure_frontend
    ensure_env
    log "${C_OK}setup OK${C_RESET} — run scripts/dev.sh to start the servers"
    exit 0
    ;;
  backend)
    ensure_env
    start_backend
    log "URL: http://localhost:8000  (logs: .logs/backend.log)"
    wait
    ;;
  frontend)
    start_frontend
    log "URL: http://localhost:5173  (logs: .logs/frontend.log)"
    wait
    ;;
  both|"")
    ensure_env
    start_backend
    start_frontend
    log ""
    log "${C_OK}both servers running${C_RESET}"
    log "  • React app    http://localhost:5173"
    log "  • Django API   http://localhost:8000/api/stats/"
    log "  • health        http://localhost:8000/api/healthz/"
    log "  • logs          tail -f $LOGDIR/{backend,frontend}.log"
    log ""
    log "press Ctrl+C to stop both"
    wait
    ;;
  *)
    die "unknown mode: '$mode' (use one of: both, backend, frontend, check)"
    ;;
esac
