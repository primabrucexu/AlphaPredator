from app.modules.jygs.request_headers import build_jygs_headers, make_jygs_token


def test_make_jygs_token_matches_browser_algorithm() -> None:
    timestamp = '1781185719708'

    token = make_jygs_token(timestamp)

    assert token == '661abae951887c634a4f51b0f333bec1'


def test_build_jygs_headers_uses_dynamic_token_and_optional_cookie() -> None:
    headers = build_jygs_headers(timestamp_ms='1781185719708', session='abc123')

    assert headers['timestamp'] == '1781185719708'
    assert headers['token'] == '661abae951887c634a4f51b0f333bec1'
    assert headers['platform'] == '3'
    assert headers['Cookie'] == 'SESSION=abc123'


def test_build_jygs_headers_omits_cookie_when_session_missing() -> None:
    headers = build_jygs_headers(timestamp_ms='1781185719708')

    assert 'Cookie' not in headers
