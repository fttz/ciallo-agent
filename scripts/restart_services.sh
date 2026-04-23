#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_LOG="$RUN_DIR/backend.log"
FRONTEND_LOG="$RUN_DIR/frontend.log"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

mkdir -p "$RUN_DIR"

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

kill_pid_file() {
  local pid_file="$1"
  local name="$2"

  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "Stopping $name (PID: $pid)..."
      kill "$pid" 2>/dev/null || true
      sleep 1
      if kill -0 "$pid" 2>/dev/null; then
        echo "$name did not stop gracefully, force killing..."
        kill -9 "$pid" 2>/dev/null || true
      fi
    fi
    rm -f "$pid_file"
  fi
}

klistening_pids() {
  local port="$1"

  if command_exists lsof; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u
    return
  fi

  if command_exists ss; then
    ss -ltnp 2>/dev/null | awk -v p=":$port" '$4 ~ p {print $NF}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' | sort -u
    return
  fi

  if command_exists netstat; then
    netstat -lntp 2>/dev/null | awk -v p=":$port" '$4 ~ p {print $7}' | cut -d/ -f1 | sed '/^-\|^$/d' | sort -u
  fi
}

kill_port() {
  local port="$1"
  local pids

  pids="$(klistening_pids "$port" || true)"
  if [[ -n "$pids" ]]; then
    echo "Releasing port $port (PIDs: $pids)..."
    for pid in $pids; do
      kill "$pid" 2>/dev/null || true
    done
    sleep 1
    for pid in $pids; do
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
    done
  fi
}

wait_for_http() {
  local url="$1"
  local name="$2"
  local attempts="${3:-30}"

  for _ in $(seq 1 "$attempts"); do
    if curl --noproxy '*' -fsS "$url" >/dev/null 2>&1; then
      echo "$name is ready: $url"
      return 0
    fi
    sleep 1
  done

  echo "$name did not become ready in time: $url"
  return 1
}

echo "Stopping existing services..."
kill_pid_file "$BACKEND_PID_FILE" "backend"
kill_pid_file "$FRONTEND_PID_FILE" "frontend"
kill_port "$BACKEND_PORT"
kill_port "$FRONTEND_PORT"

echo "Starting backend on $BACKEND_HOST:$BACKEND_PORT..."
if [[ -x "$VENV_PYTHON" ]]; then
  nohup bash -lc "cd '$ROOT_DIR/apps/api' && '$VENV_PYTHON' -m uvicorn app.main:app --host '$BACKEND_HOST' --port '$BACKEND_PORT'" >"$BACKEND_LOG" 2>&1 &
else
  nohup uv run --directory "$ROOT_DIR/apps/api" uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" >"$BACKEND_LOG" 2>&1 &
fi
BACKEND_PID=$!
echo "$BACKEND_PID" > "$BACKEND_PID_FILE"

echo "Starting frontend on $FRONTEND_HOST:$FRONTEND_PORT..."
nohup bash -lc "cd '$ROOT_DIR/apps/web' && npm run dev -- --hostname '$FRONTEND_HOST' --port '$FRONTEND_PORT'" >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$FRONTEND_PID_FILE"

wait_for_http "http://$BACKEND_HOST:$BACKEND_PORT/api/health" "Backend"
wait_for_http "http://$FRONTEND_HOST:$FRONTEND_PORT" "Frontend"

echo "Done."
echo "Backend PID:  $BACKEND_PID"
echo "Frontend PID: $FRONTEND_PID"
echo "Backend log:  $BACKEND_LOG"
echo "Frontend log: $FRONTEND_LOG"
echo

echo "Health check:"
echo "  curl --noproxy '*' http://$BACKEND_HOST:$BACKEND_PORT/api/health"
echo

echo "Follow logs:"
echo "  tail -f '$BACKEND_LOG'"
echo "  tail -f '$FRONTEND_LOG'"
