import json
from pathlib import Path

from app.modules.jygs import auth_file


def test_load_credentials_from_missing_or_invalid_file(tmp_path: Path) -> None:
    auth_path = tmp_path / 'data' / 'config' / 'jygs_auth.json'
    original_auth_file = auth_file._AUTH_FILE
    auth_file._AUTH_FILE = auth_path
    try:
        assert auth_file.load_credentials_from_file() is None

        auth_path.parent.mkdir(parents=True, exist_ok=True)
        auth_path.write_text('{invalid json', encoding='utf-8')
        assert auth_file.load_credentials_from_file() is None

        auth_path.write_text(json.dumps({'session': '   '}), encoding='utf-8')
        assert auth_file.load_credentials_from_file() is None
    finally:
        auth_file._AUTH_FILE = original_auth_file


def test_save_load_update_and_clear_credentials_file(tmp_path: Path) -> None:
    auth_path = tmp_path / 'data' / 'config' / 'jygs_auth.json'
    original_auth_file = auth_file._AUTH_FILE
    auth_file._AUTH_FILE = auth_path
    try:
        auth_file.save_credentials_to_file('session-123', expires_at='2026-12-31T00:00:00+00:00')
        loaded = auth_file.load_credentials_from_file()
        assert loaded is not None
        assert loaded['session'] == 'session-123'
        assert loaded['expires_at'] == '2026-12-31T00:00:00+00:00'
        assert loaded['is_valid'] is False

        auth_file.update_auth_check_status(True, 'ok')
        loaded_after_status = auth_file.load_credentials_from_file()
        assert loaded_after_status is not None
        assert loaded_after_status['session'] == 'session-123'
        assert loaded_after_status['is_valid'] is True
        assert loaded_after_status['last_error'] == 'ok'
        assert loaded_after_status['last_checked_at']

        auth_file.save_credentials_to_file('session-456')
        loaded_after_save = auth_file.load_credentials_from_file()
        assert loaded_after_save is not None
        assert loaded_after_save['session'] == 'session-456'
        assert loaded_after_save['is_valid'] is True
        assert loaded_after_save['last_error'] == 'ok'

        auth_file.clear_credentials_from_file()
        assert not auth_path.exists()
    finally:
        auth_file._AUTH_FILE = original_auth_file
