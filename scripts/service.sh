#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/server.pid"
LOG_FILE="$RUNTIME_DIR/server.log"
CONDA_ENV="${ROBOTCLAW_CONDA_ENV:-langchain}"
PYTHON_BIN="${ROBOTCLAW_PYTHON:-}"
PORT="${ROBOTCLAW_PORT:-8005}"

mkdir -p "$RUNTIME_DIR"

clear_logs() {
  : >"$LOG_FILE"
}

server_command() {
  if [[ -n "$PYTHON_BIN" ]]; then
    "$PYTHON_BIN" scripts/server.py
    return
  fi

  local conda_python="/opt/homebrew/Caskroom/miniforge/base/envs/$CONDA_ENV/bin/python"
  if [[ -x "$conda_python" ]]; then
    "$conda_python" scripts/server.py
    return
  fi

  if command -v conda >/dev/null 2>&1; then
    conda run --no-capture-output -n "$CONDA_ENV" python scripts/server.py
    return
  fi

  python3 scripts/server.py
}

server_command_args() {
  if [[ -n "$PYTHON_BIN" ]]; then
    printf '%q ' "$PYTHON_BIN" scripts/server.py
    return
  fi

  local conda_python="/opt/homebrew/Caskroom/miniforge/base/envs/$CONDA_ENV/bin/python"
  if [[ -x "$conda_python" ]]; then
    printf '%q ' "$conda_python" scripts/server.py
    return
  fi

  if command -v conda >/dev/null 2>&1; then
    printf '%q ' conda run --no-capture-output -n "$CONDA_ENV" python scripts/server.py
    return
  fi

  printf '%q ' python3 scripts/server.py
}

start_server_process() {
  if [[ -n "$PYTHON_BIN" ]]; then
    nohup "$PYTHON_BIN" scripts/server.py >>"$LOG_FILE" 2>&1 &
    return
  fi

  local conda_python="/opt/homebrew/Caskroom/miniforge/base/envs/$CONDA_ENV/bin/python"
  if [[ -x "$conda_python" ]]; then
    nohup "$conda_python" scripts/server.py >>"$LOG_FILE" 2>&1 &
    return
  fi

  if command -v conda >/dev/null 2>&1; then
    nohup conda run --no-capture-output -n "$CONDA_ENV" python scripts/server.py >>"$LOG_FILE" 2>&1 &
    return
  fi

  nohup python3 scripts/server.py >>"$LOG_FILE" 2>&1 &
}

find_listener_pid() {
  if ! command -v lsof >/dev/null 2>&1; then
    return 1
  fi
  lsof -tiTCP:"$PORT" -sTCP:LISTEN -nP 2>/dev/null | head -n 1
}

is_running() {
  if [[ ! -f "$PID_FILE" ]]; then
    local listener_pid
    listener_pid="$(find_listener_pid || true)"
    if [[ -n "$listener_pid" ]]; then
      echo "$listener_pid" >"$PID_FILE"
      return 0
    fi
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
  local listener_pid
  listener_pid="$(find_listener_pid || true)"
  if [[ -n "$listener_pid" ]]; then
    echo "$listener_pid" >"$PID_FILE"
    return 0
  fi
  return 1
}

start_server() {
  if is_running; then
    echo "RobotClaw server is already running (pid $(cat "$PID_FILE"))."
    return 0
  fi

  cd "$ROOT_DIR"
  clear_logs
  start_server_process
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
  __run_server)
    server_command
    ;;
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
