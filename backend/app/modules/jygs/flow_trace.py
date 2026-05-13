"""JYGS flow trace writer (redacted).

This module stores reusable request-structure events without persisting raw secrets.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from app.core.settings import settings

logger = logging.getLogger(__name__)

_SENSITIVE_HEADER_KEYS = {'cookie', 'set-cookie', 'token', 'authorization'}


def _mask_secret(value: str, keep_start: int = 4, keep_end: int = 4) -> str:
    if not value:
        return ''
    if len(value) <= keep_start + keep_end:
        return '*' * len(value)
    return f'{value[:keep_start]}***{value[-keep_end:]}'


def _mask_cookie_header(raw_cookie: str) -> str:
    items = []
    for pair in raw_cookie.split(';'):
        item = pair.strip()
        if not item:
            continue
        if '=' not in item:
            items.append(item)
            continue
        key, value = item.split('=', 1)
        key_upper = key.strip().upper()
        if key_upper == 'SESSION':
            items.append(f'{key}=<{_mask_secret(value)}>')
        else:
            items.append(f'{key}=<masked>')
    return '; '.join(items)


def sanitize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return a header map safe for persistence."""
    out: dict[str, str] = {}
    for key, value in headers.items():
        key_lower = key.lower()
        if key_lower == 'cookie':
            out[key] = _mask_cookie_header(value)
            continue
        if key_lower in {'token', 'authorization'}:
            out[key] = _mask_secret(value)
            continue
        if key_lower == 'set-cookie':
            out[key] = '<masked>'
            continue
        out[key] = value
    return out


def build_request_structure(headers: Mapping[str, str]) -> dict[str, object]:
    """Extract reusable structure hints from a request header set."""
    lower = {k.lower(): v for k, v in headers.items()}
    cookie_raw = lower.get('cookie', '')
    has_session = 'session=' in cookie_raw.lower()
    token = lower.get('token', '')
    return {
        'header_keys': sorted(list(headers.keys())),
        'auth_fields': {
            'has_session_cookie': has_session,
            'session_source': 'Cookie:SESSION (browser login state)' if has_session else 'not_observed',
            'has_token_header': bool(token),
            'token_source': 'Request header: token' if token else 'not_observed',
            'platform': lower.get('platform') or '',
            'timestamp_present': 'timestamp' in lower,
        },
        'header_setting_guide': {
            'accept': 'fixed literal',
            'content-type': 'fixed literal (json)',
            'origin_referer': 'browser origin/referrer of jiuyangongshe pages',
            'platform': 'fixed from browser call (currently observed as 3)',
            'timestamp': 'dynamic milliseconds when request is sent',
            'token': 'captured from browser request header during logged-in actions',
            'cookie_session': 'captured from SESSION cookie after web login',
        },
    }


def _trace_path() -> Path:
    return settings.jygs_flow_trace_path


def append_trace_event(event_type: str, payload: dict[str, object]) -> None:
    """Append a single redacted event line to the configured JSONL file."""
    if not settings.jygs_flow_trace_enabled:
        return

    record = {
        'time': datetime.now(timezone.utc).isoformat(),
        'event': event_type,
        'payload': payload,
    }

    path = _trace_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=True) + '\n')
    except Exception as exc:
        logger.warning('JYGS flow trace write failed: %s', exc)
