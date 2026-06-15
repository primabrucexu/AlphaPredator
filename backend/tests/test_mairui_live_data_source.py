from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from app.core.settings import settings
from app.modules.market_data import data_source


def _ensure_file_licence(monkeypatch: pytest.MonkeyPatch) -> str:
    """Use the licence currently saved in the configured file path."""
    config_path = settings.mairui_config_path
    if not config_path.exists():
        pytest.skip(f'Mairui config file not found: {config_path}')

    file_licence = str(json.loads(config_path.read_text(encoding='utf-8')).get('licence') or '').strip()
    if not file_licence:
        pytest.skip(f'Mairui licence is empty: {config_path}')

    return file_licence


def test_live_mairui_stock_list_with_current_licence(monkeypatch: pytest.MonkeyPatch) -> None:
    file_licence = _ensure_file_licence(monkeypatch)
    assert data_source._get_mairui_licence() == file_licence

    stock_df = data_source.load_stock_list()
    assert not stock_df.empty

    required_cols = {'full_code', 'code', 'name', 'is_st', 'cnspell', 'market'}
    assert required_cols.issubset(set(stock_df.columns))
    assert stock_df['full_code'].str.endswith(('.SZ', '.SH', '.BJ')).all()


def test_live_mairui_single_day_quote_with_current_licence(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_file_licence(monkeypatch)

    stock_df = data_source.load_stock_list()
    assert not stock_df.empty
    full_code = str(next(iter(stock_df['full_code'])))

    found_rows = None
    for days_back in range(0, 21):
        target_date = (date.today() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        rows = data_source._mairui_fetch_history_rows(full_code, target_date, target_date)
        if rows:
            found_rows = rows
            break

    assert found_rows, f'No daily quote found for {full_code} in last 21 days'

    first = found_rows[0]
    for key in ['full_code', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close', 'change', 'pct_chg', 'vol',
                'amount']:
        assert key in first
    assert first['full_code'] == full_code
    assert isinstance(first['close'], float)
