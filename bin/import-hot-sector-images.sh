#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE_DIR="${1:-$ROOT_DIR/data/imports/hot-sector-images}"
YEAR="${2:-$(date +%Y)}"
IMPORT_BATCH="${3:-$(basename "$IMAGE_DIR")}"

cd "$ROOT_DIR/backend"
python -m app.modules.market_data.hot_sector_importer "$IMAGE_DIR" "$YEAR" "$IMPORT_BATCH"
