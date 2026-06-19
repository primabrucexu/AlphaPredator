#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
RUNTIME_DIR="$ROOT_DIR/tmp/runtime"
LOG_DIR="$RUNTIME_DIR/logs"

PYTHON_CMD="${PYTHON:-python3}"
NODE_CMD="${NODE:-node}"
NPM_CMD="${NPM:-npm}"

BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
BACKEND_URL="http://127.0.0.1:8000/api/health"
FRONTEND_URL="http://127.0.0.1:5173"
MCP_URL="http://127.0.0.1:8000/api/mcp"

usage() {
  cat <<EOF
Usage: bin/alphapredator.sh <command>

Commands:
  check     Check Python, Node, npm and project dependency state
  install   Install backend and frontend dependencies
  start     Start backend and frontend in the background
  stop      Stop backend and frontend started by this script
  restart   Restart backend and frontend
  status    Check frontend, backend and MCP service status
EOF
}

ensure_runtime_dirs() {
  mkdir -p "$LOG_DIR"
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

version_major_minor() {
  printf '%s\n' "$1" | sed -E 's/[^0-9]*([0-9]+)\.([0-9]+).*/\1 \2/'
}

check_python() {
  if ! command_exists "$PYTHON_CMD"; then
    echo "python: missing ($PYTHON_CMD)"
    return 1
  fi

  local version major minor
  version="$("$PYTHON_CMD" --version 2>&1)"
  read -r major minor < <(version_major_minor "$version")
  if [ "${major:-0}" -lt 3 ] || { [ "${major:-0}" -eq 3 ] && [ "${minor:-0}" -lt 11 ]; }; then
    echo "python: $version (requires >= 3.11)"
    return 1
  fi

  echo "python: $version"
}

check_node() {
  if ! command_exists "$NODE_CMD"; then
    echo "node: missing ($NODE_CMD)"
    return 1
  fi
  if ! command_exists "$NPM_CMD"; then
    echo "npm: missing ($NPM_CMD)"
    return 1
  fi

  local version major
  version="$("$NODE_CMD" --version 2>&1)"
  major="$(printf '%s\n' "$version" | sed -E 's/v?([0-9]+).*/\1/')"
  if [ "${major:-0}" -lt 18 ]; then
    echo "node: $version (requires >= 18)"
    return 1
  fi

  echo "node: $version"
  echo "npm: $("${NPM_CMD}" --version)"
}

check_dependencies() {
  if [ -x "$BACKEND_DIR/.venv/bin/python" ]; then
    echo "backend dependencies: installed"
  else
    echo "backend dependencies: missing"
  fi

  if [ -d "$FRONTEND_DIR/node_modules" ]; then
    echo "frontend dependencies: installed"
  else
    echo "frontend dependencies: missing"
  fi
}

check() {
  local failed=0
  check_python || failed=1
  check_node || failed=1
  check_dependencies
  return "$failed"
}

install_backend() {
  echo "Installing backend dependencies..."
  cd "$BACKEND_DIR"
  if [ ! -d ".venv" ]; then
    "$PYTHON_CMD" -m venv .venv
  fi
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -e ".[dev]"
}

install_frontend() {
  echo "Installing frontend dependencies..."
  cd "$FRONTEND_DIR"
  "$NPM_CMD" install
}

install_all() {
  check_python
  check_node
  install_backend
  install_frontend
}

is_pid_running() {
  local pid_file="$1"
  [ -f "$pid_file" ] || return 1

  local pid
  pid="$(cat "$pid_file")"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" >/dev/null 2>&1
}

start_service() {
  local name="$1"
  local pid_file="$2"
  local command_path="$3"
  local log_file="$LOG_DIR/$name.log"

  if is_pid_running "$pid_file"; then
    echo "$name: already running (pid $(cat "$pid_file"))"
    return 0
  fi

  echo "Starting $name..."
  nohup "$command_path" >"$log_file" 2>&1 &
  echo "$!" >"$pid_file"

  sleep 0.5
  if ! is_pid_running "$pid_file"; then
    echo "$name: failed to start (log $log_file)" >&2
    rm -f "$pid_file"
    return 1
  fi

  echo "$name: started (pid $(cat "$pid_file"), log $log_file)"
}

start_all() {
  ensure_runtime_dirs
  start_service "backend" "$BACKEND_PID_FILE" "$ROOT_DIR/bin/dev-backend.sh"
  start_service "frontend" "$FRONTEND_PID_FILE" "$ROOT_DIR/bin/dev-frontend.sh"
}

stop_service() {
  local name="$1"
  local pid_file="$2"

  if ! is_pid_running "$pid_file"; then
    echo "$name: not running"
    rm -f "$pid_file"
    return 0
  fi

  local pid
  pid="$(cat "$pid_file")"
  echo "Stopping $name (pid $pid)..."
  kill "$pid"

  local attempts=0
  while kill -0 "$pid" >/dev/null 2>&1 && [ "$attempts" -lt 20 ]; do
    sleep 0.5
    attempts=$((attempts + 1))
  done

  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "$name: did not stop gracefully, sending SIGKILL"
    kill -9 "$pid"
  fi

  rm -f "$pid_file"
  echo "$name: stopped"
}

stop_all() {
  stop_service "frontend" "$FRONTEND_PID_FILE"
  stop_service "backend" "$BACKEND_PID_FILE"
}

restart_all() {
  stop_all
  start_all
}

http_status() {
  local url="$1"
  shift
  if ! command_exists curl; then
    echo "000"
    return 0
  fi
  local code
  code="$(curl -sS -o /dev/null -w "%{http_code}" "$@" "$url" 2>/dev/null || true)"
  if [ -z "$code" ]; then
    echo "000"
  else
    echo "$code"
  fi
}

print_status_line() {
  local name="$1"
  local code="$2"
  local ok_codes="$3"
  local url="$4"

  case " $ok_codes " in
    *" $code "*)
      echo "$name: ok ($code) $url"
      ;;
    *)
      echo "$name: unavailable ($code) $url"
      ;;
  esac
}

status_all() {
  local backend_code frontend_code mcp_code
  backend_code="$(http_status "$BACKEND_URL")"
  frontend_code="$(http_status "$FRONTEND_URL")"
  mcp_code="$(http_status "$MCP_URL" -H "Accept: text/event-stream")"

  print_status_line "backend" "$backend_code" "200" "$BACKEND_URL"
  print_status_line "frontend" "$frontend_code" "200 301 302 304" "$FRONTEND_URL"

  if [ "$mcp_code" = "000" ] || [ "$mcp_code" = "404" ]; then
    echo "mcp: unavailable ($mcp_code) $MCP_URL"
  else
    echo "mcp: mounted ($mcp_code) $MCP_URL"
  fi
}

main() {
  local command="${1:-}"
  case "$command" in
    check)
      check
      ;;
    install)
      install_all
      ;;
    start)
      start_all
      ;;
    stop)
      stop_all
      ;;
    restart)
      restart_all
      ;;
    status)
      status_all
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      echo "Unknown command: $command" >&2
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
