import asyncio
from pathlib import Path

from app.modules.jygs import auth as auth_module
from app.modules.jygs.flow_trace import build_request_structure, sanitize_headers


def test_sanitize_headers_and_build_request_structure_mask_secrets() -> None:
    headers = {
        'Cookie': 'SESSION=abcdef123456; foo=bar',
        'token': 'token-secret',
        'Authorization': 'Bearer abc',
        'Set-Cookie': 'SESSION=whatever',
        'platform': '3',
        'timestamp': '1234567890',
        'Accept': 'application/json',
    }

    sanitized = sanitize_headers(headers)
    assert sanitized['Cookie'].startswith('SESSION=<abcd***3456>')
    assert 'foo=<masked>' in sanitized['Cookie']
    assert sanitized['token'] == 'toke***cret'
    assert sanitized['Authorization'] == 'Bear*** abc'
    assert sanitized['Set-Cookie'] == '<masked>'

    structure = build_request_structure(headers)
    assert structure['auth_fields']['has_session_cookie'] is True
    assert structure['auth_fields']['has_token_header'] is True
    assert structure['auth_fields']['platform'] == '3'
    assert structure['auth_fields']['timestamp_present'] is True


def test_auth_get_session_and_probe_skip_when_no_credentials() -> None:
    original_load = auth_module.load_credentials_from_file
    original_append = auth_module.append_trace_event
    events: list[tuple[str, dict]] = []
    auth_module.load_credentials_from_file = lambda: None
    auth_module.append_trace_event = lambda event_type, payload: events.append((event_type, payload))
    try:
        assert auth_module.get_session() is None
        valid, detail = asyncio.run(auth_module.check_credentials_valid())
        assert valid is False
        assert 'SESSION' in detail
        assert events and events[0][0] == 'probe_skipped'
        assert events[0][1]['reason'] == 'no_session_in_auth_file'
    finally:
        auth_module.load_credentials_from_file = original_load
        auth_module.append_trace_event = original_append
