"""韭研公社登录凭据管理。

凭据文件存储于 data/config/jygs.credentials（JSON 格式），包含：
  - session: SESSION Cookie 的值
  - saved_at: 保存时间（ISO 8601）
  - expires_at: 估算过期时间（ISO 8601），可为 null
"""

import json
import logging
from datetime import datetime, timezone

import httpx

from app.core.settings import settings

logger = logging.getLogger(__name__)

_CREDENTIALS_PATH = settings.jygs_credentials_path

# 用于验证凭据有效性的轻量探测接口
_PROBE_URL = f'{settings.jygs_api_url}/api/v1/action/field'
_PROBE_PAYLOAD = {'date': '2026-01-02', 'pc': 1}


# ---------------------------------------------------------------------------
# 凭据的读写
# ---------------------------------------------------------------------------

def load_credentials() -> dict | None:
    """读取本地存储的凭据，若不存在返回 None。"""
    if not _CREDENTIALS_PATH.exists():
        return None
    try:
        return json.loads(_CREDENTIALS_PATH.read_text(encoding='utf-8'))
    except Exception:
        return None


def save_credentials(session: str, expires_at: str | None = None) -> None:
    """保存 SESSION 凭据到本地文件。"""
    _CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        'session': session,
        'saved_at': datetime.now(timezone.utc).isoformat(),
        'expires_at': expires_at,
    }
    _CREDENTIALS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    logger.info('JYGS credentials saved.')


def clear_credentials() -> None:
    """删除本地凭据文件。"""
    if _CREDENTIALS_PATH.exists():
        _CREDENTIALS_PATH.unlink()
        logger.info('JYGS credentials cleared.')


def get_session() -> str | None:
    """获取已保存的 SESSION 值，若无则返回 None。"""
    creds = load_credentials()
    return creds.get('session') if creds else None


# ---------------------------------------------------------------------------
# 凭据有效性验证
# ---------------------------------------------------------------------------

async def check_credentials_valid() -> bool:
    """
    发送一个轻量探测请求，验证已保存的 SESSION 是否仍然有效。
    返回 True 表示有效，False 表示无效或未配置。
    """
    session = get_session()
    if not session:
        return False
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(
                _PROBE_URL,
                json=_PROBE_PAYLOAD,
                headers={
                    'Cookie': f'SESSION={session}',
                    'User-Agent': (
                        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                        'AppleWebKit/605.1.15 (KHTML, like Gecko) '
                        'Version/17.0 Mobile/15E148 Safari/604.1'
                    ),
                    'Referer': settings.jygs_site_url,
                },
            )
            data = resp.json()
            return data.get('errCode') == '0'
    except Exception as exc:
        logger.warning('JYGS credentials probe failed: %s', exc)
        return False

