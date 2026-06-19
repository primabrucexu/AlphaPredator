#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
PYTHON_BIN="$BACKEND_DIR/.venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Backend virtualenv not found. Run: $ROOT_DIR/bin/alphapredator.sh install" >&2
  exit 1
fi

cd "$BACKEND_DIR"
exec "$PYTHON_BIN" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
