#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "Frontend dependencies not found. Run: $ROOT_DIR/bin/alphapredator.sh install" >&2
  exit 1
fi

cd "$FRONTEND_DIR"
exec "${NPM:-npm}" run dev -- --host 0.0.0.0 --port 5173
