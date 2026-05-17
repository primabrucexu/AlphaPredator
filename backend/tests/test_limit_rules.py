"""Unit tests for the limit_rules module (涨跌停计算规则)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.modules.market_data.limit_rules import (
    BOARD_BSE,
    BOARD_CHINEXT,
    BOARD_MAIN,
    BOARD_STAR,
    LIMIT_RULE_VERSION,
    compute_limit_fields,
    detect_board,
    detect_is_st,
    is_no_limit_day,
)


# ---------------------------------------------------------------------------
# detect_board
# ---------------------------------------------------------------------------


class TestDetectBoard:
    def test_sz_main_board_0xxx(self) -> None:
        assert detect_board('000001.SZ') == BOARD_MAIN

    def test_sz_main_board_1xxx(self) -> None:
        assert detect_board('100056.SZ') == BOARD_MAIN

    def test_sz_main_board_2xxx(self) -> None:
        assert detect_board('200002.SZ') == BOARD_MAIN

    def test_sz_chinext_3xxx(self) -> None:
        assert detect_board('300308.SZ') == BOARD_CHINEXT

    def test_sz_chinext_301xxx(self) -> None:
        assert detect_board('301015.SZ') == BOARD_CHINEXT

    def test_sh_main_board_6xxx(self) -> None:
        assert detect_board('600036.SH') == BOARD_MAIN

    def test_sh_star_688xxx(self) -> None:
        assert detect_board('688001.SH') == BOARD_STAR

    def test_sh_star_689xxx(self) -> None:
        assert detect_board('689009.SH') == BOARD_STAR

    def test_bj_exchange(self) -> None:
        assert detect_board('830799.BJ') == BOARD_BSE

    def test_bj_4xxx(self) -> None:
        assert detect_board('430047.BJ') == BOARD_BSE

    def test_unknown_exchange(self) -> None:
        assert detect_board('000001.XX') is None

    def test_malformed_full_code(self) -> None:
        assert detect_board('000001') is None

    def test_sh_non_6_prefix(self) -> None:
        # SH codes starting with something other than 6 or 688/689 are unknown
        assert detect_board('500001.SH') is None


# ---------------------------------------------------------------------------
# detect_is_st
# ---------------------------------------------------------------------------


class TestDetectIsST:
    def test_st_prefix(self) -> None:
        assert detect_is_st('ST股票') is True

    def test_star_st_prefix(self) -> None:
        assert detect_is_st('*ST公司') is True

    def test_sst_prefix(self) -> None:
        assert detect_is_st('SST特别') is True

    def test_s_star_st_prefix(self) -> None:
        assert detect_is_st('S*ST退市') is True

    def test_normal_name(self) -> None:
        assert detect_is_st('平安银行') is False

    def test_empty_name(self) -> None:
        assert detect_is_st('') is False

    def test_trailing_whitespace(self) -> None:
        assert detect_is_st('  *ST公司') is True  # strip() applied


# ---------------------------------------------------------------------------
# is_no_limit_day
# ---------------------------------------------------------------------------


class TestIsNoLimitDay:
    def _patch_trading(self, trading_dates: set[str]):
        """Patch _is_trading_day_local to treat only listed dates as trading days."""

        def mock_trading(d: date) -> bool:
            return d.strftime('%Y%m%d') in trading_dates

        return patch(
            'app.modules.market_data.limit_rules._is_trading_day_local',
            side_effect=mock_trading,
        )

    def test_returns_false_when_list_date_none(self) -> None:
        assert is_no_limit_day('20240102', None) is False

    def test_returns_false_when_list_date_empty(self) -> None:
        assert is_no_limit_day('20240102', '') is False

    def test_returns_false_when_trade_date_before_list_date(self) -> None:
        assert is_no_limit_day('20240101', '20240102') is False

    def test_first_trading_day_is_no_limit(self) -> None:
        # Listing date is a trading day
        trading = {'20240102'}
        with self._patch_trading(trading):
            assert is_no_limit_day('20240102', '20240102') is True

    def test_fifth_trading_day_is_no_limit(self) -> None:
        # 5 consecutive trading days
        trading = {'20240102', '20240103', '20240104', '20240105', '20240108'}
        with self._patch_trading(trading):
            assert is_no_limit_day('20240108', '20240102') is True

    def test_sixth_trading_day_has_limits(self) -> None:
        trading = {
            '20240102', '20240103', '20240104',
            '20240105', '20240108', '20240109',
        }
        with self._patch_trading(trading):
            assert is_no_limit_day('20240109', '20240102') is False

    def test_far_future_date_has_limits(self) -> None:
        # list_date 2020-01-02, trade_date 2024-01-02 → way past window
        assert is_no_limit_day('20240102', '20200102') is False


# ---------------------------------------------------------------------------
# compute_limit_fields
# ---------------------------------------------------------------------------


class TestComputeLimitFields:

    # --- NORMAL path: main board ---

    def test_main_board_normal(self) -> None:
        result = compute_limit_fields(
            full_code='000001.SZ',
            trade_date='20240102',
            pre_close=10.0,
            close=10.5,
        )
        assert result['limit_status'] == 'NORMAL'
        assert result['limit_rule'] == BOARD_MAIN
        assert result['limit_pct'] == Decimal('0.10')
        # 10.0 * 1.1 = 11.0, ROUND_HALF_UP → 11.00
        assert result['limit_up_price'] == Decimal('11.00')
        # 10.0 * 0.9 = 9.0, ROUND_HALF_UP → 9.00
        assert result['limit_down_price'] == Decimal('9.00')
        assert result['is_limit_up'] == 0
        assert result['is_limit_down'] == 0
        assert result['limit_rule_version'] == LIMIT_RULE_VERSION

    def test_main_board_limit_up_hit(self) -> None:
        result = compute_limit_fields(
            full_code='000001.SZ',
            trade_date='20240102',
            pre_close=10.0,
            close=11.0,  # exactly at limit_up
        )
        assert result['is_limit_up'] == 1
        assert result['is_limit_down'] == 0

    def test_main_board_limit_down_hit(self) -> None:
        result = compute_limit_fields(
            full_code='000001.SZ',
            trade_date='20240102',
            pre_close=10.0,
            close=9.0,  # exactly at limit_down
        )
        assert result['is_limit_up'] == 0
        assert result['is_limit_down'] == 1

    def test_main_board_rounding_half_up(self) -> None:
        # 10.05 * 1.1 = 11.055 → ROUND_HALF_UP to 11.06
        result = compute_limit_fields(
            full_code='600036.SH',
            trade_date='20240102',
            pre_close=10.05,
            close=10.0,
        )
        assert result['limit_up_price'] == Decimal('11.06')

    # --- NORMAL path: ChiNext ---

    def test_chinext_board_20pct(self) -> None:
        result = compute_limit_fields(
            full_code='300308.SZ',
            trade_date='20240102',
            pre_close=20.0,
            close=22.0,
        )
        assert result['limit_rule'] == BOARD_CHINEXT
        assert result['limit_pct'] == Decimal('0.20')
        assert result['limit_up_price'] == Decimal('24.00')
        assert result['limit_down_price'] == Decimal('16.00')

    # --- NORMAL path: STAR market ---

    def test_star_market_20pct(self) -> None:
        result = compute_limit_fields(
            full_code='688001.SH',
            trade_date='20240102',
            pre_close=100.0,
            close=110.0,
        )
        assert result['limit_rule'] == BOARD_STAR
        assert result['limit_pct'] == Decimal('0.20')
        assert result['limit_up_price'] == Decimal('120.00')
        assert result['limit_down_price'] == Decimal('80.00')

    # --- NORMAL path: BSE (向下取整) ---

    def test_bse_30pct_floor_rounding(self) -> None:
        # 10.0 * 1.3 = 13.0 exactly, no rounding needed
        result = compute_limit_fields(
            full_code='830799.BJ',
            trade_date='20240102',
            pre_close=10.0,
            close=10.5,
        )
        assert result['limit_rule'] == BOARD_BSE
        assert result['limit_pct'] == Decimal('0.30')
        assert result['limit_up_price'] == Decimal('13.00')
        assert result['limit_down_price'] == Decimal('7.00')

    def test_bse_floor_rounding_applied(self) -> None:
        # 10.05 * 1.3 = 13.065 → ROUND_FLOOR → 13.06
        result = compute_limit_fields(
            full_code='830799.BJ',
            trade_date='20240102',
            pre_close=10.05,
            close=11.0,
        )
        assert result['limit_up_price'] == Decimal('13.06')

    # --- INVALID cases ---

    def test_invalid_when_pre_close_zero(self) -> None:
        result = compute_limit_fields(
            full_code='000001.SZ',
            trade_date='20240102',
            pre_close=0.0,
            close=10.0,
        )
        assert result['limit_status'] == 'INVALID'
        assert result['limit_up_price'] is None
        assert result['limit_down_price'] is None
        assert result['is_limit_up'] == 0
        assert result['is_limit_down'] == 0

    def test_invalid_when_pre_close_none(self) -> None:
        result = compute_limit_fields(
            full_code='000001.SZ',
            trade_date='20240102',
            pre_close=None,
            close=10.0,
        )
        assert result['limit_status'] == 'INVALID'

    def test_invalid_when_board_unrecognised(self) -> None:
        result = compute_limit_fields(
            full_code='000001.XX',
            trade_date='20240102',
            pre_close=10.0,
            close=10.0,
        )
        assert result['limit_status'] == 'INVALID'

    # --- NO_LIMIT cases ---

    def test_no_limit_day(self) -> None:
        # list_date == trade_date → first trading day
        with patch(
            'app.modules.market_data.limit_rules._is_trading_day_local',
            return_value=True,
        ):
            result = compute_limit_fields(
                full_code='000001.SZ',
                trade_date='20240102',
                pre_close=10.0,
                close=15.0,
                list_date='20240102',
            )
        assert result['limit_status'] == 'NO_LIMIT'
        assert result['limit_up_price'] is None
        assert result['limit_down_price'] is None
        assert result['is_limit_up'] == 0
        assert result['is_limit_down'] == 0

    # --- ST detection ---

    def test_st_detected_from_name(self) -> None:
        result = compute_limit_fields(
            full_code='000001.SZ',
            trade_date='20240102',
            pre_close=10.0,
            close=10.5,
            stock_name='*ST公司',
        )
        assert result['is_st'] == 1
        assert result['st_source'] == 'name_prefix'

    def test_non_st_name(self) -> None:
        result = compute_limit_fields(
            full_code='000001.SZ',
            trade_date='20240102',
            pre_close=10.0,
            close=10.5,
            stock_name='平安银行',
        )
        assert result['is_st'] == 0
        assert result['st_source'] == ''

    # --- limit_down_price floor at 0.01 ---

    def test_limit_down_floor_at_min_price(self) -> None:
        # Very low price stock; raw limit_down should be floored at 0.01
        result = compute_limit_fields(
            full_code='000001.SZ',
            trade_date='20240102',
            pre_close=0.02,  # 0.02 * 0.9 = 0.018 → rounds to 0.02, not below 0.01
            close=0.02,
        )
        assert result['limit_status'] == 'NORMAL'
        assert result['limit_down_price'] >= Decimal('0.01')
