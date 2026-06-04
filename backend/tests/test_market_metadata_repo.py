from pathlib import Path

from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.repositories.market_metadata_repo import MarketMetadataRepo


def test_build_stock_name_map_zfills_code_and_ignores_blank_name(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.sqlite3'
    ensure_sqlite_schema(sqlite_path)

    conn = connect_sqlite(sqlite_path)
    try:
        conn.executemany(
            '''
            INSERT INTO stock_list (full_code, code, name, is_st, cnspell, market)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            [
                ('000001.SZ', '1', 'PingAn', 0, 'PAYH', 'main'),
                ('000002.SZ', '000002', '', 0, 'VANKE', 'main'),
                ('600000.SH', '600000', 'PfBank', 0, 'PFYH', 'main'),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    repo = MarketMetadataRepo(sqlite_path)
    assert repo.build_stock_name_map() == {
        '000001': 'PingAn',
        '600000': 'PfBank',
    }
