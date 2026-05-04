#!/usr/bin/env python3
"""Import stock list CSV to SQLite."""

from datetime import datetime, timezone
from app.api.routes.data_init import _read_stock_list_csv
from app.core.settings import settings
from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.modules.market_data.data_source import _REQUIRED_STOCK_LIST_COLS

# 读取 CSV 文件
csv_path = settings.stock_list_path
contents = csv_path.read_bytes()

df = _read_stock_list_csv(contents)

# 检查必需的列
missing = _REQUIRED_STOCK_LIST_COLS - set(df.columns)
if missing:
    raise ValueError(f'CSV is missing required columns: {sorted(missing)}')

# 导入到 SQLite
uploaded_at = datetime.now(timezone.utc).isoformat()
ensure_sqlite_schema()
conn = connect_sqlite()
try:
    conn.execute('DELETE FROM stock_universe')

    # 补充缺失的列
    fill_cols = {c: '' for c in ['cnspell', 'market', 'list_status', 'list_date', 'delist_date']
                 if c not in df.columns}
    for col, default in fill_cols.items():
        df[col] = default

    # 处理 cnspell（拼音简称）
    df['cnspell'] = df['cnspell'].fillna('').astype(str).str.strip().str.upper()

    # 准备要插入的行
    rows_to_insert = [
        (
            str(r.ts_code or '').strip(),
            str(r.symbol or '').strip(),
            str(r.name or '').strip(),
            str(r.cnspell or ''),
            str(r.market or '').strip(),
            str(r.list_status or '').strip(),
            str(r.list_date or '').strip(),
            str(r.delist_date or '').strip(),
            uploaded_at,
        )
        for r in df[['ts_code', 'symbol', 'name', 'cnspell', 'market',
                     'list_status', 'list_date', 'delist_date']].itertuples(index=False)
    ]

    # 批量插入
    conn.executemany(
        '''INSERT OR REPLACE INTO stock_universe
           (ts_code, symbol, name, cnspell, market, list_status, list_date, delist_date, uploaded_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        rows_to_insert,
    )
    conn.commit()

    # 验证导入结果
    count = conn.execute('SELECT COUNT(*) FROM stock_universe').fetchone()[0]
    print(f"Successfully imported {count} stocks to SQLite stock_universe")

finally:
    conn.close()

