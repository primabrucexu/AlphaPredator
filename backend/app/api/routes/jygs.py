"""韭研公社鉴权路由（Playwright 登录 + 手动 SESSION）。"""

import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.modules.jygs.auth import (
    check_credentials_valid,
    clear_credentials,
    load_credentials,
    save_credentials,
)
from app.modules.jygs.flow_trace import append_trace_event
from app.modules.jygs.playwright_login import login_and_capture_session

logger = logging.getLogger(__name__)
router = APIRouter()


@router.api_route('/proxy', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'HEAD', 'PATCH'])
@router.api_route('/proxy/{path:path}', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'HEAD', 'PATCH'])
async def retired_proxy(path: str = '') -> JSONResponse:
    """Proxy flow is retired; login now uses local Playwright browser."""
    logger.info('JYGS proxy route requested but retired: %s', path)
    return JSONResponse(
        {'ok': False, 'error': '代理登录已下线，请使用 Playwright 一键登录。'},
        status_code=410,
    )


# ---------------------------------------------------------------------------
# 鉴权管理接口（手动 SESSION）
# ---------------------------------------------------------------------------

class SaveSessionRequest(BaseModel):
    session: str


class PlaywrightLoginRequest(BaseModel):
    timeout_seconds: int = 300


@router.post('/auth/login/playwright', status_code=200)
async def login_with_playwright(body: PlaywrightLoginRequest) -> JSONResponse:
    """Launch a local Playwright browser for manual login and capture SESSION automatically."""
    timeout_seconds = max(30, min(int(body.timeout_seconds), 900))
    trace_id = uuid4().hex
    append_trace_event('playwright_login_start', {
        'trace_id': trace_id,
        'timeout_seconds': timeout_seconds,
        'how_to_get': 'User completes login in Playwright-opened web page; SESSION is read from browser cookies.',
    })
    try:
        result = await asyncio.to_thread(login_and_capture_session, timeout_seconds)
        session = str(result.get('session') or '').strip()
        if not session:
            raise RuntimeError('未捕获到 SESSION')
        save_credentials(session)
        valid, detail = await check_credentials_valid()
        if not valid:
            clear_credentials()
            append_trace_event('playwright_login_finish', {
                'trace_id': trace_id,
                'ok': False,
                'error': detail,
            })
            return JSONResponse({'ok': False, 'error': f'登录后校验失败：{detail}'}, status_code=400)

        append_trace_event('credentials_capture', {
            'trace_id': trace_id,
            'source': 'playwright_browser_cookie',
            'credential': 'SESSION',
            'value_preview': f'{session[:4]}***{session[-4:]}' if len(session) >= 8 else '*' * len(session),
            'value_length': len(session),
            'how_to_get': 'Captured from Playwright browser cookie after user completed web login.',
        })
        append_trace_event('playwright_login_finish', {
            'trace_id': trace_id,
            'ok': True,
            'detail': detail,
            'cookie_count': result.get('cookie_count', 0),
        })
        return JSONResponse({'ok': True, 'detail': detail})
    except Exception as exc:
        append_trace_event('playwright_login_finish', {
            'trace_id': trace_id,
            'ok': False,
            'error': str(exc),
        })
        logger.warning('JYGS Playwright login failed: %s', exc)
        return JSONResponse({'ok': False, 'error': f'Playwright 登录失败：{exc}'}, status_code=500)


@router.get('/auth/status')
async def get_auth_status() -> JSONResponse:
    """返回韭研公社凭据的当前状态。"""
    logger.info('JYGS auth/status requested')
    creds = load_credentials()
    if not creds:
        logger.info('JYGS auth/status: no credentials file found')
        return JSONResponse({'configured': False, 'valid': False, 'saved_at': None})

    valid, detail = await check_credentials_valid()
    logger.info('JYGS auth/status result. valid=%s detail=%s', valid, detail)
    return JSONResponse({
        'configured': True,
        'valid': valid,
        'saved_at': creds.get('saved_at'),
        'expires_at': creds.get('expires_at'),
    })


@router.post('/auth/session', status_code=200)
async def save_session(body: SaveSessionRequest) -> JSONResponse:
    """
    手动保存 SESSION 并验证有效性。
    保存前发送轻量探针到韭研公社 API，结果完整记录到后端日志。
    """
    session = body.session.strip()
    logger.info('JYGS save_session called. session_length=%d session_prefix=%.8s…', len(session), session or '(empty)')

    if not session:
        logger.warning('JYGS save_session rejected: empty session')
        return JSONResponse({'ok': False, 'error': 'SESSION 不能为空'}, status_code=400)

    save_credentials(session)
    append_trace_event('credentials_capture', {
        'trace_id': uuid4().hex,
        'source': 'manual_api_submit',
        'credential': 'SESSION',
        'value_preview': f'{session[:4]}***{session[-4:]}' if len(session) >= 8 else '*' * len(session),
        'value_length': len(session),
        'how_to_get': 'User pasted SESSION from browser cookie and submitted to /api/jygs/auth/session.',
    })
    logger.info('JYGS save_session: credentials written, starting probe…')

    valid, detail = await check_credentials_valid()
    logger.info('JYGS save_session probe done. valid=%s detail=%s', valid, detail)

    if not valid:
        clear_credentials()
        logger.warning('JYGS save_session: credentials cleared due to invalid probe. detail=%s', detail)
        return JSONResponse(
            {'ok': False, 'error': f'SESSION 无效：{detail}'},
            status_code=400,
        )

    logger.info('JYGS save_session: SUCCESS. detail=%s', detail)
    return JSONResponse({'ok': True, 'detail': detail})


@router.delete('/auth/session', status_code=200)
async def delete_session() -> JSONResponse:
    """清除已保存的韭研公社凭据。"""
    logger.info('JYGS delete_session called')
    clear_credentials()
    append_trace_event('credentials_cleared', {
        'trace_id': uuid4().hex,
        'credential': 'SESSION',
        'reason': 'manual_delete_api',
    })
    return JSONResponse({'ok': True})
