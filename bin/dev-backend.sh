#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR/backend"

.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
