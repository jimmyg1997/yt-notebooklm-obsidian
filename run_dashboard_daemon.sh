#!/usr/bin/env bash
# Start or restart the vault dashboard (http://localhost:8787)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Missing .venv — run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
mkdir -p .dashboard
PORT="${DASHBOARD_PORT:-8787}"

stop_old() {
  if lsof -ti:"$PORT" >/dev/null 2>&1; then
    echo "Stopping old dashboard on :$PORT…"
    lsof -ti:"$PORT" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
}

wait_ready() {
  for _ in $(seq 1 20); do
    if curl -sf "http://127.0.0.1:${PORT}/api/vaults" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

start_detached() {
  # Fully detach from the launching terminal (VS Code task shells send SIGHUP on close).
  nohup "$PYTHON" run_dashboard.sh >> .dashboard/dashboard.log 2>&1 < /dev/null &
  local pid=$!
  disown -h "$pid" 2>/dev/null || true
  echo "$pid"
}

restart() {
  stop_old
  local pid
  pid="$(start_detached)"
  echo "Dashboard starting (PID $pid) — http://127.0.0.1:${PORT}"
  if wait_ready; then
    echo "Dashboard ready."
  else
    echo "ERROR: Dashboard did not respond. Last log lines:" >&2
    tail -15 .dashboard/dashboard.log >&2 || true
    exit 1
  fi
  echo "Logs: .dashboard/dashboard.log"
}

case "${1:-start}" in
  restart|--restart|-r)
    restart
    ;;
  stop)
    stop_old
    echo "Stopped."
    ;;
  start)
    if lsof -ti:"$PORT" >/dev/null 2>&1; then
      echo "Dashboard already running on :$PORT. Use: ./run_dashboard_daemon.sh restart"
      exit 0
    fi
    restart
    ;;
  *)
    echo "Usage: $0 [start|restart|stop]" >&2
    exit 1
    ;;
esac
