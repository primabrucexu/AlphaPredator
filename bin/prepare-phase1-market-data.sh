#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export ROOT_DIR

"$ROOT_DIR/backend/.venv/bin/python" - <<'PY'
import csv
import json
import os
from pathlib import Path

root_dir = Path(os.environ['ROOT_DIR'])
batch_dir = root_dir / 'data' / 'imports' / 'market-data' / 'sample-batch'
batch_dir.mkdir(parents=True, exist_ok=True)

stock_pool_rows = [
    {
        'stock_code': '000001',
        'stock_name': '平安银行',
        'sectors': '银行',
        'ai_quick_summary': '量能保持平稳，适合作为防御型观察样本。',
    },
    {
        'stock_code': '300308',
        'stock_name': '中际旭创',
        'sectors': 'AI 算力|CPO',
        'ai_quick_summary': '算力主线延续，趋势与量能共振，但不宜在加速段盲目追高。',
    },
    {
        'stock_code': '601138',
        'stock_name': '工业富联',
        'sectors': '算力|服务器',
        'ai_quick_summary': '板块辨识度较高，适合跟踪是否继续放量突破。',
    },
]

daily_snapshot_rows = [
    {
        'trade_date': '2026-04-30',
        'stock_code': '000001',
        'current_price': '11.28',
        'change_amount': '0.14',
        'change_pct': '1.24',
        'turnover_amount_billion': '31.70',
        'turnover_rate': '0.91',
    },
    {
        'trade_date': '2026-04-30',
        'stock_code': '300308',
        'current_price': '167.53',
        'change_amount': '5.93',
        'change_pct': '3.66',
        'turnover_amount_billion': '82.40',
        'turnover_rate': '5.24',
    },
    {
        'trade_date': '2026-04-30',
        'stock_code': '601138',
        'current_price': '26.17',
        'change_amount': '0.61',
        'change_pct': '2.39',
        'turnover_amount_billion': '45.20',
        'turnover_rate': '1.74',
    },
]

daily_bar_rows = [
    {'stock_code': '000001', 'trade_date': '2026-04-24', 'open_price': '10.92', 'high_price': '11.05', 'low_price': '10.86', 'close_price': '10.97', 'volume': '51230000'},
    {'stock_code': '000001', 'trade_date': '2026-04-25', 'open_price': '10.98', 'high_price': '11.08', 'low_price': '10.91', 'close_price': '11.02', 'volume': '49820000'},
    {'stock_code': '000001', 'trade_date': '2026-04-28', 'open_price': '11.03', 'high_price': '11.13', 'low_price': '10.95', 'close_price': '11.08', 'volume': '53410000'},
    {'stock_code': '000001', 'trade_date': '2026-04-29', 'open_price': '11.06', 'high_price': '11.16', 'low_price': '11.01', 'close_price': '11.12', 'volume': '47650000'},
    {'stock_code': '000001', 'trade_date': '2026-04-30', 'open_price': '11.13', 'high_price': '11.31', 'low_price': '11.08', 'close_price': '11.28', 'volume': '56340000'},
    {'stock_code': '300308', 'trade_date': '2026-04-24', 'open_price': '157.60', 'high_price': '160.20', 'low_price': '156.80', 'close_price': '159.40', 'volume': '18320000'},
    {'stock_code': '300308', 'trade_date': '2026-04-25', 'open_price': '159.80', 'high_price': '162.60', 'low_price': '158.90', 'close_price': '161.70', 'volume': '19180000'},
    {'stock_code': '300308', 'trade_date': '2026-04-28', 'open_price': '162.10', 'high_price': '164.30', 'low_price': '160.70', 'close_price': '163.50', 'volume': '20540000'},
    {'stock_code': '300308', 'trade_date': '2026-04-29', 'open_price': '163.80', 'high_price': '166.10', 'low_price': '162.90', 'close_price': '165.40', 'volume': '21490000'},
    {'stock_code': '300308', 'trade_date': '2026-04-30', 'open_price': '165.90', 'high_price': '168.40', 'low_price': '164.70', 'close_price': '167.53', 'volume': '22860000'},
    {'stock_code': '601138', 'trade_date': '2026-04-24', 'open_price': '24.85', 'high_price': '25.14', 'low_price': '24.71', 'close_price': '24.98', 'volume': '72540000'},
    {'stock_code': '601138', 'trade_date': '2026-04-25', 'open_price': '25.01', 'high_price': '25.33', 'low_price': '24.95', 'close_price': '25.21', 'volume': '74810000'},
    {'stock_code': '601138', 'trade_date': '2026-04-28', 'open_price': '25.25', 'high_price': '25.64', 'low_price': '25.11', 'close_price': '25.48', 'volume': '78130000'},
    {'stock_code': '601138', 'trade_date': '2026-04-29', 'open_price': '25.56', 'high_price': '25.92', 'low_price': '25.41', 'close_price': '25.56', 'volume': '76280000'},
    {'stock_code': '601138', 'trade_date': '2026-04-30', 'open_price': '25.61', 'high_price': '26.28', 'low_price': '25.48', 'close_price': '26.17', 'volume': '80550000'},
]

hot_sectors_payload = {
    'trade_date': '2026-04-30',
    'items': [
        {'name': '算力', 'trend_label': '持续 3 日', 'heat_score': 93},
        {'name': '机器人', 'trend_label': '持续 2 日', 'heat_score': 88},
        {'name': '军工', 'trend_label': '新晋热点', 'heat_score': 74},
    ],
}

with (batch_dir / 'stock_pool.csv').open('w', encoding='utf-8', newline='') as file:
    writer = csv.DictWriter(file, fieldnames=['stock_code', 'stock_name', 'sectors', 'ai_quick_summary'])
    writer.writeheader()
    writer.writerows(stock_pool_rows)

with (batch_dir / 'daily_stock_snapshots.csv').open('w', encoding='utf-8', newline='') as file:
    writer = csv.DictWriter(
        file,
        fieldnames=['trade_date', 'stock_code', 'current_price', 'change_amount', 'change_pct', 'turnover_amount_billion', 'turnover_rate'],
    )
    writer.writeheader()
    writer.writerows(daily_snapshot_rows)

with (batch_dir / 'daily_bars.csv').open('w', encoding='utf-8', newline='') as file:
    writer = csv.DictWriter(
        file,
        fieldnames=['stock_code', 'trade_date', 'open_price', 'high_price', 'low_price', 'close_price', 'volume'],
    )
    writer.writeheader()
    writer.writerows(daily_bar_rows)

(batch_dir / 'hot_sectors.json').write_text(json.dumps(hot_sectors_payload, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Prepared sample batch at {batch_dir}')
PY

"$ROOT_DIR/bin/import-market-data.sh" "$ROOT_DIR/data/imports/market-data/sample-batch"
