"""韭研公社登录凭据管理。

存储：JSON 文件 (data/config/jygs_auth.json)

探针接口：app.jiuyangongshe.com/jystock-app/api/v1/action/diagram-url
  errCode == "0"  → SESSION 有效
  其他 / 302重定向 → SESSION 失效或无权限
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.modules.jygs.auth_file import load_credentials_from_file, save_credentials_to_file, clear_credentials_from_file
from app.modules.jygs.flow_trace import append_trace_event, build_request_structure, sanitize_headers
from app.modules.jygs.request_headers import build_jygs_headers, make_timestamp_ms

logger = logging.getLogger(__name__)

# 按浏览器抓包命令使用 app 域名 + jystock-app 路径
_PROBE_URL = 'https://app.jiuyangongshe.com/jystock-app/api/v1/action/diagram-url'
def _preview_secret(value: str) -> str:
    if not value:
        return ''
    if len(value) <= 8:
        return '*' * len(value)
    return f'{value[:4]}***{value[-4:]}'


# ---------------------------------------------------------------------------
# 凭据的读写
# ---------------------------------------------------------------------------

def load_credentials() -> dict | None:
    """从 JSON 文件读取凭据，若无记录返回 None。"""
    return load_credentials_from_file()


def save_credentials(session: str, expires_at: str | None = None) -> None:
    """将 SESSION 写入 JSON 文件。"""
    try:
        save_credentials_to_file(session, expires_at)
        logger.info('JYGS credentials saved to JSON file. session_length=%d', len(session))
    except Exception as exc:
        logger.error('JYGS save_credentials failed: %s', exc)
        raise


def clear_credentials() -> None:
    """清空 JSON 文件中的凭据。"""
    try:
        clear_credentials_from_file()
        logger.info('JYGS credentials cleared.')
    except Exception as exc:
        logger.warning('JYGS clear_credentials failed: %s', exc)


def get_session() -> str | None:
    """获取已保存的 SESSION 原始值（不含 SESSION= 前缀）。"""
    creds = load_credentials()
    return creds.get('session') if creds else None


# ---------------------------------------------------------------------------
# 凭据有效性验证
# ---------------------------------------------------------------------------

async def check_credentials_valid() -> tuple[bool, str]:
    """
    调用 diagram-url 探针验证 SESSION 有效性。
    返回 (valid: bool, detail: str)。
    """
    session = get_session()
    trace_id = uuid4().hex
    if not session:
        logger.warning('JYGS probe skipped: no session in auth file')
        append_trace_event('probe_skipped', {
            'trace_id': trace_id,
            'reason': 'no_session_in_auth_file',
        })
        return False, '未找到已保存的 SESSION'

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    probe_url = _PROBE_URL
    timestamp_ms = make_timestamp_ms()
    logger.info('JYGS probe start. url=%s session_length=%d date=%s timestamp=%s', probe_url, len(session), today,
                timestamp_ms)
    probe_headers = build_jygs_headers(timestamp_ms=timestamp_ms, session=session)
    append_trace_event('probe_request', {
        'trace_id': trace_id,
        'url': probe_url,
        'method': 'POST',
        'json_keys': ['date'],
        'request_headers': sanitize_headers(probe_headers),
        'request_structure': build_request_structure(probe_headers),
        'credential_sources': {
            'session': 'Loaded from data/config/jygs_auth.json',
            'token': 'Generated from browser algorithm: md5("Uu0KfOB8iUP69d3c:" + timestamp)',
        },
        'credential_preview': {
            'session': _preview_secret(session),
            'token': _preview_secret(probe_headers['token']),
        },
    })

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            resp = await client.post(
                probe_url,
                json={'date': today},
                headers=probe_headers,
            )

        logger.info('JYGS probe response. status=%d body_preview=%s', resp.status_code, resp.text[:300])

        if resp.is_redirect or resp.status_code in (301, 302, 303, 401, 403):
            location = resp.headers.get('location', '')
            logger.warning('JYGS probe auth failure. status=%d location=%s', resp.status_code, location)
            append_trace_event('probe_response', {
                'trace_id': trace_id,
                'status_code': resp.status_code,
                'result': 'redirect_or_auth_failure',
                'location': location,
                'body_preview': resp.text[:120],
            })
            return False, f'SESSION 已失效（HTTP {resp.status_code} 重定向至 {location}）'

        data = resp.json()
        err_code = str(data.get('errCode', '')).strip()
        msg = str(data.get('msg', '')).strip()
        logger.info('JYGS probe errCode=%s msg=%.80s', err_code, msg)

        if err_code == '0':
            logger.info('JYGS SESSION valid.')
            append_trace_event('probe_response', {
                'trace_id': trace_id,
                'status_code': resp.status_code,
                'result': 'valid',
                'err_code': err_code,
                'msg': msg[:120],
            })
            return True, 'errCode=0'

        logger.warning('JYGS probe invalid. errCode=%s msg=%.80s', err_code, msg)
        append_trace_event('probe_response', {
            'trace_id': trace_id,
            'status_code': resp.status_code,
            'result': 'invalid',
            'err_code': err_code,
            'msg': msg[:120],
        })
        if err_code == '9':
            return False, f'韭研请求 token 无效（errCode={err_code}，{msg}）'
        return False, f'韭研认证探针失败（errCode={err_code}，{msg}）'

    except httpx.RequestError as exc:
        logger.warning('JYGS probe network error: %s', exc)
        append_trace_event('probe_response', {
            'trace_id': trace_id,
            'result': 'network_error',
            'error': str(exc),
        })
        return False, f'网络请求失败：{exc}'
    except Exception as exc:
        logger.warning('JYGS probe unexpected error: %s', exc)
        append_trace_event('probe_response', {
            'trace_id': trace_id,
            'result': 'unexpected_error',
            'error': str(exc),
        })
        return False, f'验证异常：{exc}'
