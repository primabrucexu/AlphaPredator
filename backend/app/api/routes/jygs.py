"""韭研公社反向代理 + 鉴权路由。

代理路径：
  GET/POST /api/jygs/proxy/{path}  →  转发到 https://www.jiuyangongshe.com/{path}

鉴权接口：
  GET  /api/jygs/auth/status   →  返回当前凭据状态
  POST /api/jygs/auth/session  →  手动保存 SESSION（控制台方式兜底）
  DELETE /api/jygs/auth/session →  清除凭据

代理工作原理：
  1. 前端弹出窗口访问 /api/jygs/proxy/
  2. 后端将请求转发给韭研公社，并把 Set-Cookie 响应头里的 SESSION 保存下来
  3. HTML 响应会重写绝对 URL，让页面内的跳转/资源继续走代理
  4. 一旦捕获到 SESSION，重定向到 /jygs-login-success（前端路由）
  5. 前端轮询 /api/jygs/auth/status 检测到成功后关闭弹窗
"""

import logging
import re
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from app.modules.jygs.auth import (
    check_credentials_valid,
    clear_credentials,
    load_credentials,
    save_credentials,
)
from app.core.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# 韭研公社网站根地址（用于代理）
_JYGS_SITE = settings.jygs_site_url  # https://www.jiuyangongshe.com

# 我们代理的本地路径前缀（用于 URL 重写）
_PROXY_PREFIX = '/api/jygs/proxy'

# 登录成功后跳转的前端路由（React 路由，显示"连接成功"提示）
_SUCCESS_REDIRECT = '/initialize?jygs_login=success'

# 浏览器常用 User-Agent（移动端，匹配韭研公社预期的客户端类型）
_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
    'AppleWebKit/605.1.15 (KHTML, like Gecko) '
    'Version/17.0 Mobile/15E148 Safari/604.1'
)

# 不向目标服务器转发的请求头（避免暴露代理身份或引起冲突）
_SKIP_REQ_HEADERS = frozenset({
    'host', 'origin', 'referer', 'content-length',
    'transfer-encoding', 'connection', 'upgrade-insecure-requests',
})

# 不向浏览器转发的响应头（避免浏览器误用目标服务器的 CORS/安全策略）
_SKIP_RESP_HEADERS = frozenset({
    'content-encoding', 'transfer-encoding', 'connection',
    'content-security-policy', 'x-frame-options',
    'strict-transport-security',
})


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _rewrite_url_to_proxy(url: str) -> str:
    """把 https://www.jiuyangongshe.com/xxx 重写为 /api/jygs/proxy/xxx。"""
    if url.startswith(_JYGS_SITE):
        path = url[len(_JYGS_SITE):]
        return f'{_PROXY_PREFIX}{path or "/"}'
    return url


def _rewrite_html(html: str) -> str:
    """
    重写 HTML 内容，将韭研公社的绝对 URL 替换为代理路径，
    并注入 <base> 标签确保相对路径也走代理。
    """
    # 替换 href/src/action 属性中的绝对 URL
    def replace_attr(m: re.Match) -> str:
        attr, url = m.group(1), m.group(2)
        return f'{attr}="{_rewrite_url_to_proxy(str(url))}"'

    html = re.sub(
        r'(href|src|action)=["\'](https?://(?:www|app)\.jiuyangongshe\.com[^"\']*)["\']',
        replace_attr,
        html,
    )

    # 注入 <base> 标签，让相对路径走代理
    base_tag = f'<base href="{_PROXY_PREFIX}/">'
    if '<head>' in html:
        html = html.replace('<head>', f'<head>\n{base_tag}', 1)
    elif '<HEAD>' in html:
        html = html.replace('<HEAD>', f'<HEAD>\n{base_tag}', 1)

    return html


def _extract_session_from_headers(set_cookie_headers: list[str]) -> str | None:
    """从 Set-Cookie 响应头列表中提取 SESSION 的值。"""
    for header in set_cookie_headers:
        for part in header.split(';'):
            part = part.strip()
            if part.upper().startswith('SESSION='):
                return part.split('=', 1)[1]
    return None


def _build_proxy_headers(request: Request) -> dict:
    """构建转发给韭研公社的请求头。"""
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in _SKIP_REQ_HEADERS
    }
    headers['User-Agent'] = _UA
    headers['Referer'] = _JYGS_SITE + '/'
    headers['Origin'] = _JYGS_SITE
    return headers


# ---------------------------------------------------------------------------
# 代理路由
# ---------------------------------------------------------------------------

@router.api_route(
    '/proxy/{path:path}',
    methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'HEAD', 'PATCH'],
)
async def jygs_proxy(path: str, request: Request) -> Response:
    """将请求代理到韭研公社，同时监听 SESSION Cookie 的出现。"""
    target_url = f'{_JYGS_SITE}/{path}'
    if request.query_params:
        target_url += '?' + str(request.query_params)

    body = await request.body()
    headers = _build_proxy_headers(request)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20,
            verify=True,
        ) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body if body else None,
            )
    except httpx.RequestError as exc:
        logger.error('JYGS proxy request failed: %s', exc)
        return Response(
            content=f'代理请求失败：{exc}'.encode(),
            status_code=502,
        )

    # ── 检测 SESSION Cookie ─────────────────────────────────────────────
    set_cookie_values = resp.headers.get_list('set-cookie')
    session = _extract_session_from_headers(set_cookie_values)
    if session:
        save_credentials(session)
        logger.info('JYGS SESSION captured via proxy.')
        # 登录成功，把弹窗引导到成功页（React 路由）
        return RedirectResponse(url=_SUCCESS_REDIRECT, status_code=302)

    # ── 构建响应头（过滤不安全的头） ─────────────────────────────────────
    resp_headers: dict[str, str] = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in _SKIP_RESP_HEADERS
    }

    # ── HTML 内容重写 ──────────────────────────────────────────────────
    content_type = resp.headers.get('content-type', '')
    if 'text/html' in content_type:
        html = resp.text
        html = _rewrite_html(html)
        return HTMLResponse(
            content=html,
            status_code=resp.status_code,
            headers=resp_headers,
        )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=content_type or None,
        headers=resp_headers,
    )


# ---------------------------------------------------------------------------
# 鉴权管理接口
# ---------------------------------------------------------------------------

class SaveSessionRequest(BaseModel):
    session: str


@router.get('/auth/status')
async def get_auth_status() -> JSONResponse:
    """
    返回韭研公社凭据的当前状态。
    前端启动弹窗后轮询此接口，检测是否已成功捕获到凭据。
    """
    creds = load_credentials()
    if not creds:
        return JSONResponse({'configured': False, 'valid': False, 'saved_at': None})

    valid = await check_credentials_valid()
    return JSONResponse({
        'configured': True,
        'valid': valid,
        'saved_at': creds.get('saved_at'),
        'expires_at': creds.get('expires_at'),
    })


@router.post('/auth/session', status_code=200)
async def save_session(body: SaveSessionRequest) -> JSONResponse:
    """
    手动保存 SESSION（兜底方案：用户从浏览器控制台复制后提交）。
    保存前会验证凭据有效性。
    """
    session = body.session.strip()
    if not session:
        return JSONResponse({'ok': False, 'error': 'SESSION 不能为空'}, status_code=400)

    # 暂存并验证
    save_credentials(session)
    valid = await check_credentials_valid()
    if not valid:
        clear_credentials()
        return JSONResponse(
            {'ok': False, 'error': 'SESSION 无效，请确认已登录韭研公社后重试'},
            status_code=400,
        )

    return JSONResponse({'ok': True})


@router.delete('/auth/session', status_code=200)
async def delete_session() -> JSONResponse:
    """清除已保存的韭研公社凭据。"""
    clear_credentials()
    return JSONResponse({'ok': True})



