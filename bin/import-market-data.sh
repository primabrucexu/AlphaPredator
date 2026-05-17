#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BATCH_DIR="${1:-$ROOT_DIR/data/imports/market-data/manual-batch}"

cd "$ROOT_DIR/backend"
python -m app.modules.market_data.importer "$BATCH_DIR"
