from pathlib import Path

from app.db.sqlite import ensure_sqlite_schema
from app.repositories.jygs_repo import JygsRepo


def test_jygs_repo_auth_and_sync_log(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'jygs-repo.db'
    ensure_sqlite_schema(sqlite_path)

    repo = JygsRepo(sqlite_path)
    assert repo.get_auth_row() is None

    repo.save_auth_cookie('SESSION=abc', '2026-05-10T00:00:00Z')
    auth = repo.get_auth_row()
    assert auth is not None
    assert auth['auth_cookie'] == 'SESSION=abc'

    repo.update_auth_check_status('2026-05-10T01:00:00Z', True, '')
    auth = repo.get_auth_row()
    assert auth is not None
    assert int(auth['is_valid']) == 1

    assert not repo.has_sync_slot('2026-05-10@12:02')
    repo.upsert_sync_log(
        slot_key='2026-05-10@12:02',
        trade_date='2026-05-10',
        mode='INCREMENTAL',
        status='SUCCESS',
        message='',
        triggered_at='2026-05-10T12:02:00+08:00',
    )
    assert repo.has_sync_slot('2026-05-10@12:02')
