#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/server.pid"
LOG_FILE="$RUNTIME_DIR/server.log"

mkdir -p "$RUNTIME_DIR"

is_running() {
  if [[ ! -f "$PID_FILE" ]]; then
    return 1
  fi

  local pid
  pid="$(cat "$PID_FILE")"
  if [[ -z "$pid" ]]; then
    return 1
  fi

  if kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi

  rm -f "$PID_FILE"
  return 1
}

start_server() {
  if is_running; then
    echo "RobotClaw server is already running (pid $(cat "$PID_FILE"))."
    return 0
  fi

  cd "$ROOT_DIR"
  nohup python3 scripts/server.py >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  echo "RobotClaw server started (pid $(cat "$PID_FILE"))."
  echo "Log: $LOG_FILE"
}

stop_server() {
  if ! is_running; then
    echo "RobotClaw server is not running."
    return 0
  fi

  local pid
  pid="$(cat "$PID_FILE")"
  kill "$pid"

  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if ! kill -0 "$pid" >/dev/null 2>&1; then
      rm -f "$PID_FILE"
      echo "RobotClaw server stopped."
      return 0
    fi
    sleep 1
  done

  echo "Server did not stop gracefully, sending SIGKILL."
  kill -9 "$pid"
  rm -f "$PID_FILE"
  echo "RobotClaw server stopped."
}

status_server() {
  if is_running; then
    echo "RobotClaw server is running (pid $(cat "$PID_FILE"))."
  else
    echo "RobotClaw server is not running."
  fi
}

restart_server() {
  stop_server
  start_server
}

case "${1:-}" in
  start)
    start_server
    ;;
  stop)
    stop_server
    ;;
  restart)
    restart_server
    ;;
  status)
    status_server
    ;;
  *)
    echo "Usage: bash scripts/service.sh {start|stop|restart|status}"
    exit 1
    ;;
esac
