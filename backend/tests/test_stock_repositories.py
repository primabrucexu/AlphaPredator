from pathlib import Path
from uuid import uuid4

from app.db.sqlite import ensure_sqlite_schema
from app.repositories.stock_list_repo import StockListRepo


def test_stock_list_repo_replace_and_lookup() -> None:
    sqlite_path = Path(__file__).parents[2] / 'tmp' / f'stock-list-{uuid4().hex}.db'
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
    assert repo.list_for_search('000001.SZ', limit=10)[0]['code'] == '000001'
    assert repo.list_for_search('SZ000001', limit=10)[0]['code'] == '000001'
    assert repo.list_for_search('平安', limit=10)[0]['code'] == '000001'
    assert repo.has_rows() is True
    assert repo.count_rows() == 2
    assert repo.get_board_counts() == {'主板': 1, '创业板': 1}

