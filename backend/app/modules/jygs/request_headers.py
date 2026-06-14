"""韭研公社 API 请求头构造。"""

from __future__ import annotations

import hashlib
import time

_BROWSER_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0'
)
_SEC_CH_UA = '"Chromium";v="149", "Microsoft Edge";v="149", "Not/A)Brand";v="99"'
_PLATFORM = '3'
_TOKEN_SALT = 'Uu0KfOB8iUP69d3c'


def make_jygs_token(timestamp_ms: str) -> str:
    """按网页端算法生成 token：md5("<salt>:<timestamp>")."""
    raw = f'{_TOKEN_SALT}:{timestamp_ms}'.encode('utf-8')
    return hashlib.md5(raw).hexdigest()  # noqa: S324 - mirrors upstream browser signing.


def make_timestamp_ms() -> str:
    return str(int(time.time() * 1000))


def build_jygs_headers(*, timestamp_ms: str | None = None, session: str | None = None) -> dict[str, str]:
    timestamp = timestamp_ms or make_timestamp_ms()
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'DNT': '1',
        'Pragma': 'no-cache',
        'Referer': 'https://www.jiuyangongshe.com/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'User-Agent': _BROWSER_UA,
        'platform': _PLATFORM,
        'sec-ch-ua': _SEC_CH_UA,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'timestamp': timestamp,
        'token': make_jygs_token(timestamp),
    }
    if session:
        headers['Cookie'] = f'SESSION={session}'
    return headers
