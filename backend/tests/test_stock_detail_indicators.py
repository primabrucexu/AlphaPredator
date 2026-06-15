from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.market_data.service import MarketDataService


def test_stock_detail_indicators_use_expma_macd8_17_6_and_kdj6_3_3(tmp_path: Path) -> None:
    service = MarketDataService(sqlite_path=tmp_path / 'test.db', duckdb_path=tmp_path / 'test.duckdb')
    bars = [
        {
            'close_price': float(10 + idx),
            'high_price': float(11 + idx),
            'low_price': float(9 + idx),
            'volume': float(1000 + idx),
        }
        for idx in range(8)
    ]

    indicators = service._build_indicator_series(bars)

    assert set(['expma8', 'expma17', 'expma21', 'expma55']).issubset(indicators)
    assert 'ma5' not in indicators
    assert indicators['expma8'][0] == 10.0
    assert indicators['expma8'][1] == pytest.approx(round((2 / 9) * 11 + (7 / 9) * 10, 2))

    ema8 = service._compute_ema_series([float(10 + idx) for idx in range(8)], 8)
    ema17 = service._compute_ema_series([float(10 + idx) for idx in range(8)], 17)
    dif_raw = [ema8[i] - ema17[i] for i in range(8)]
    dea_raw = service._compute_ema_series(dif_raw, 6)
    assert indicators['macd_dif'][1] == pytest.approx(round(dif_raw[1], 4))
    assert indicators['macd_dea'][1] == pytest.approx(round(dea_raw[1], 4))
    assert indicators['macd_hist'][1] == pytest.approx(round((dif_raw[1] - dea_raw[1]) * 2, 4))

    assert indicators['kdj_k'][:5] == [None, None, None, None, None]
    assert indicators['kdj_k'][5] is not None
