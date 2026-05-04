#!/usr/bin/env python3
"""Generate stock list CSV from DuckDB data."""

import csv
from app.core.settings import settings
from app.db.duckdb_storage import connect_duckdb

# 获取 DuckDB 中的所有股票
duckdb_conn = connect_duckdb(settings.duckdb_path)
stocks = duckdb_conn.execute(
    'SELECT DISTINCT stock_code FROM daily_bars ORDER BY stock_code'
).fetchall()
duckdb_conn.close()

print(f"Found {len(stocks)} stocks in DuckDB")

# 生成 CSV 文件
csv_path = settings.stock_list_path
csv_path.parent.mkdir(parents=True, exist_ok=True)

with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    # 写入表头
    writer.writerow(['ts_code', 'symbol', 'name', 'market', 'list_status', 'cnspell', 'list_date', 'delist_date'])

    # 写入股票数据
    for (stock_code,) in stocks:
        symbol = str(stock_code)
        # 根据股票代码推断市场
        if symbol.startswith('0') or symbol.startswith('3'):
            ts_code = f"{symbol}.SZ"  # 深圳：主板 0，创业板 3
            market = "深京沪A"
        elif symbol.startswith('6'):
            ts_code = f"{symbol}.SH"  # 上海：主板 6
            market = "深京沪A"
        elif symbol.startswith('8'):
            ts_code = f"{symbol}.BJ"  # 北京
            market = "北交所"
        else:
            ts_code = f"{symbol}.SZ"
            market = "深京沪A"

        writer.writerow([
            ts_code,           # ts_code
            symbol,            # symbol
            f"Stock_{symbol}", # name（使用默认名称）
            market,            # market
            'L',               # list_status（上市）
            '',                # cnspell（空值）
            '20200101',        # list_date（默认日期）
            ''                 # delist_date（空值）
        ])

print(f"Stock list CSV created at {csv_path}")

