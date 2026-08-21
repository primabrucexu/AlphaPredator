from __future__ import annotations

from app.database.models import JygsCredential
from app.jygs.client import parse_records, sync_range
from app.jygs.playwright_browser import browser_channel_candidates


def test_parse_jygs_records_merges_themes():
    payload = {"data": [
        {"name": "白酒", "list": [{"code": "600519", "name": "贵州茅台", "article": {"action_info": {
            "time": "10:30", "num": "首板", "expound": "业绩增长"
        }}}]},
        {"name": "消费", "list": [{"code": "SH600519", "name": "贵州茅台", "article": {"action_info": {}}}]},
    ]}
    rows = parse_records("2026-08-15", payload)
    assert len(rows) == 1
    assert rows[0].stock_code == "600519"
    assert rows[0].hot_theme == "消费、白酒"
    assert rows[0].reason == "业绩增长"


def test_browser_channels_prefer_configured_value(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSER_CHANNEL", "chrome")
    assert browser_channel_candidates() == ["chrome"]


def test_sync_range_allows_more_than_366_days(db, monkeypatch):
    db.add(JygsCredential(id=1, session="test-session"))
    db.commit()
    monkeypatch.setattr("app.jygs.client._post", lambda *_args, **_kwargs: {"data": []})

    result = sync_range(db, "2024-01-01", "2025-01-02")

    assert result == {"days": 368, "records": 0}
