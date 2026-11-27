#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${EIP_VENV:-$HOME/dev/venvs/cassini}"
UVICORN_BIN="$VENV_DIR/bin/uvicorn"

API_HOST="${EIP_API_HOST:-127.0.0.1}"
API_PORT="${EIP_API_PORT:-8000}"
UI_HOST="${EIP_UI_HOST:-127.0.0.1}"
UI_PORT="${EIP_UI_PORT:-5173}"
export EIP_EVIDENCE_PATH="${EIP_EVIDENCE_PATH:-sample_data/evidence.json}"
export VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://localhost:${API_PORT}}"

if [[ ! -x "$UVICORN_BIN" ]]; then
  echo "Error: uvicorn not found at $UVICORN_BIN" >&2
  echo "Create the virtualenv and install dependencies first (see README.md)." >&2
  exit 1
fi

if [[ ! -d "$SCRIPT_DIR/dashboard/node_modules" ]]; then
  echo "Error: dashboard/node_modules not found." >&2
  echo "Run 'cd dashboard && npm ci' first (see README.md)." >&2
  exit 1
fi

API_PID=""
UI_PID=""

cleanup() {
  local exit_code=$?
  trap - INT TERM EXIT
  echo ""
  echo "Shutting down EIP services..."
  if [[ -n "$UI_PID" ]] && kill -0 "$UI_PID" 2>/dev/null; then
    kill -TERM -- "-$UI_PID" 2>/dev/null || kill -TERM "$UI_PID" 2>/dev/null || true
  fi
  if [[ -n "$API_PID" ]] && kill -0 "$API_PID" 2>/dev/null; then
    kill -TERM -- "-$API_PID" 2>/dev/null || kill -TERM "$API_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
  exit "$exit_code"
}

trap cleanup INT TERM EXIT

cd "$SCRIPT_DIR"

echo "Starting EIP API on http://${API_HOST}:${API_PORT} (evidence: ${EIP_EVIDENCE_PATH})..."
setsid "$UVICORN_BIN" api.main:app --host "$API_HOST" --port "$API_PORT" &
API_PID=$!

# Wait for API health check before launching UI
for _ in $(seq 1 40); do
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "Error: EIP API exited unexpectedly during startup." >&2
    exit 1
  fi
  if curl -sf "http://${API_HOST}:${API_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

echo "Starting Evidence Inspector UI on http://${UI_HOST}:${UI_PORT} (API: ${VITE_API_BASE_URL})..."
setsid bash -c 'cd "$1" && exec npm run dev -- --host "$2" --port "$3"' _ \
  "$SCRIPT_DIR/dashboard" "$UI_HOST" "$UI_PORT" &
UI_PID=$!

echo ""
echo "EIP v0.3.0 is running (Ctrl+C to stop both services):"
echo "  API:       http://${API_HOST}:${API_PORT}  (OpenAPI: http://${API_HOST}:${API_PORT}/docs)"
echo "  Dashboard: http://${UI_HOST}:${UI_PORT}"
echo ""

wait -n "$API_PID" "$UI_PID"
