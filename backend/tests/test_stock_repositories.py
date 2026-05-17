from pathlib import Path

from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.repositories.stock_list_repo import StockListRepo
from app.repositories.stock_profile_repo import StockProfileRepo


def test_stock_list_repo_replace_and_lookup(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'stock-list.db'
    ensure_sqlite_schema(sqlite_path)
    repo = StockListRepo(sqlite_path)

    repo.replace_all(
        [
            ('000001.SZ', '000001', '平安银行', 0, 'PAYH', '主板'),
            ('300308.SZ', '300308', '中际旭创', 0, 'ZJXC', '创业板'),
        ]
    )

    assert repo.get_by_full_code_upper('000001.SZ') is not None
    assert len(repo.list_by_code('000001')) == 1
    assert len(repo.list_by_cnspell_exact('PAYH')) == 1
    assert len(repo.list_by_cnspell_prefix('ZJ', limit=10)) == 1
    assert len(repo.list_for_search('300', limit=10)) == 1
    assert repo.has_rows() is True
    assert repo.count_rows() == 2
    assert repo.get_board_counts() == {'主板': 1, '创业板': 1}


def test_stock_profile_repo_get_profile(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'stock-profile.db'
    ensure_sqlite_schema(sqlite_path)

    list_repo = StockListRepo(sqlite_path)
    list_repo.replace_all(
        [('000001.SZ', '000001', '平安银行', 0, 'PAYH', '主板')]
    )

    # write profile through direct SQL path still used in updater/importer

    conn = connect_sqlite(sqlite_path)
    try:
        conn.execute(
            '''INSERT INTO stock_profiles (stock_code, stock_name, sectors_json, ai_quick_summary)
               VALUES (?, ?, ?, ?)''',
            ('000001', '平安银行', '["银行"]', '摘要'),
        )
        conn.commit()
    finally:
        conn.close()

    profile_repo = StockProfileRepo(sqlite_path)
    profile = profile_repo.get_profile('000001')
    assert profile is not None
    assert profile['stock_name'] == '平安银行'
