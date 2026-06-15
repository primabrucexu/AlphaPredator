from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.modules.market_data import mairui_config


def test_save_and_load_mairui_json_config(tmp_path) -> None:
    config_path = tmp_path / 'mairui.json'
    fake_settings = SimpleNamespace(
        mairui_config_path=config_path,
        market_data_rate_limit=1000,
        mairui_fetch_concurrency=4,
    )

    with patch.object(mairui_config, 'settings', fake_settings):
        saved = mairui_config.save_mairui_config(
            licence=' LICENCE ',
            rate_limit_per_minute=1200,
            fetch_concurrency=6,
        )
        loaded = mairui_config.load_mairui_config()

    raw = json.loads(config_path.read_text(encoding='utf-8'))
    assert saved.licence == 'LICENCE'
    assert loaded.licence == 'LICENCE'
    assert loaded.rate_limit_per_minute == 1200
    assert loaded.fetch_concurrency == 6
    assert raw['licence'] == 'LICENCE'
    assert raw['rate_limit_per_minute'] == 1200
    assert raw['fetch_concurrency'] == 6
    assert raw['updated_at']


def test_load_mairui_config_uses_defaults_when_json_missing(tmp_path) -> None:
    fake_settings = SimpleNamespace(
        mairui_config_path=tmp_path / 'missing.json',
        market_data_rate_limit=1000,
        mairui_fetch_concurrency=4,
    )

    with patch.object(mairui_config, 'settings', fake_settings):
        loaded = mairui_config.load_mairui_config()

    assert loaded.licence == ''
    assert loaded.rate_limit_per_minute == 1000
    assert loaded.fetch_concurrency == 4


def test_mairui_config_rejects_invalid_rate_or_concurrency(tmp_path) -> None:
    fake_settings = SimpleNamespace(
        mairui_config_path=tmp_path / 'mairui.json',
        market_data_rate_limit=1000,
        mairui_fetch_concurrency=4,
    )

    with patch.object(mairui_config, 'settings', fake_settings):
        with pytest.raises(ValueError, match='rate_limit_per_minute'):
            mairui_config.save_mairui_config(
                licence='LICENCE',
                rate_limit_per_minute=0,
                fetch_concurrency=4,
            )
        with pytest.raises(ValueError, match='fetch_concurrency'):
            mairui_config.save_mairui_config(
                licence='LICENCE',
                rate_limit_per_minute=1000,
                fetch_concurrency=0,
            )
