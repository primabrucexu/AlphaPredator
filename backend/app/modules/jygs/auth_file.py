"""韭研公社认证 JSON 文件存储模块。

存储位置：data/config/jygs_auth.json

JSON 格式：
{
    "session": "xxxx...",
    "saved_at": "2026-05-19T10:30:45.123456",
    "expires_at": null,
    "is_valid": false,
    "last_checked_at": "2026-05-19T10:35:00",
    "last_error": ""
}
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# 认证文件存储路径
_AUTH_FILE = Path(__file__).parent.parent.parent.parent / 'data' / 'config' / 'jygs_auth.json'


def _ensure_config_dir() -> None:
    """确保 data/config 目录存在。"""
    _AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_credentials_from_file() -> dict | None:
    """从 JSON 文件读取认证凭据。

    Returns:
        {
            'session': 'xxxx...',
            'saved_at': '2026-05-19T...',
            'expires_at': None or str,
            'is_valid': bool,
            'last_checked_at': str or None,
            'last_error': str
        }
        or None if file doesn't exist or is invalid
    """
    try:
        if not _AUTH_FILE.exists():
            logger.debug('JYGS auth file not found: %s', _AUTH_FILE)
            return None

        with open(_AUTH_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        session = data.get('session', '').strip()
        if not session:
            logger.warning('JYGS auth file: session field is empty')
            return None

        logger.info('JYGS credentials loaded from file. session_len=%d', len(session))
        return {
            'session': session,
            'saved_at': str(data.get('saved_at', '')),
            'expires_at': data.get('expires_at'),
            'is_valid': bool(data.get('is_valid', False)),
            'last_checked_at': data.get('last_checked_at'),
            'last_error': str(data.get('last_error', '')),
        }
    except json.JSONDecodeError as e:
        logger.warning('JYGS auth file JSON decode error: %s', e)
        return None
    except Exception as e:
        logger.warning('JYGS load_credentials_from_file failed: %s', e)
        return None


def save_credentials_to_file(session: str, expires_at: str | None = None) -> None:
    """将认证写入 JSON 文件。

    Args:
        session: SESSION 值（不含前缀）
        expires_at: 过期时间（可选）
    """
    _ensure_config_dir()

    session = session.strip()
    if not session:
        logger.warning('JYGS save_credentials_to_file: session is empty')
        return

    try:
        # 读取现有数据，保留验证状态
        existing_data = {}
        if _AUTH_FILE.exists():
            try:
                with open(_AUTH_FILE, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except Exception:
                existing_data = {}

        # 更新 session，保留验证状态不变
        data = {
            'session': session,
            'saved_at': datetime.now(timezone.utc).isoformat(),
            'expires_at': expires_at,
            'is_valid': existing_data.get('is_valid', False),
            'last_checked_at': existing_data.get('last_checked_at'),
            'last_error': existing_data.get('last_error', ''),
        }

        with open(_AUTH_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info('JYGS credentials saved to file: %s (session_len=%d)', _AUTH_FILE, len(session))
    except Exception as e:
        logger.error('JYGS save_credentials_to_file failed: %s', e)
        raise


def update_auth_check_status(is_valid: bool, last_error: str = '') -> None:
    """更新认证验证状态。

    Args:
        is_valid: 认证是否有效
        last_error: 最后一次检查的错误信息
    """
    _ensure_config_dir()

    try:
        # 读取现有数据
        data = {}
        if _AUTH_FILE.exists():
            try:
                with open(_AUTH_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}

        # 仅更新验证状态，保留 session 等信息不变
        data['is_valid'] = is_valid
        data['last_checked_at'] = datetime.now(timezone.utc).isoformat()
        data['last_error'] = last_error

        with open(_AUTH_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info('JYGS auth check status updated: is_valid=%s', is_valid)
    except Exception as e:
        logger.error('JYGS update_auth_check_status failed: %s', e)


def clear_credentials_from_file() -> None:
    """删除认证文件。"""
    try:
        if _AUTH_FILE.exists():
            _AUTH_FILE.unlink()
            logger.info('JYGS auth file deleted: %s', _AUTH_FILE)
    except Exception as e:
        logger.warning('JYGS clear_credentials_from_file failed: %s', e)


