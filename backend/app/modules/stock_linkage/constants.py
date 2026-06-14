from __future__ import annotations

SINGLE_BAR_RETURN = 'single_bar_return'
INTRADAY_RETURN_FROM_PRE_CLOSE = 'intraday_return_from_pre_close'

A_SINGLE_BAR_THRESHOLDS = (0.02, 0.03, 0.04, 0.05)
A_INTRADAY_THRESHOLDS = (0.03, 0.05, 0.07, 0.09)
B_TARGET_THRESHOLDS = (0.02, 0.03, 0.04, 0.05)

T_DAY_HIGH = 't_day_high'
T_DAY_CLOSE = 't_day_close'
NEXT_DAY_HIGH = 'next_day_high'
NEXT_DAY_CLOSE = 'next_day_close'
OBSERVATION_TYPES = (T_DAY_HIGH, T_DAY_CLOSE, NEXT_DAY_HIGH, NEXT_DAY_CLOSE)

MANUAL_SINGLE = 'manual_single'
HOT_LIMIT_TOP = 'hot_limit_top'
