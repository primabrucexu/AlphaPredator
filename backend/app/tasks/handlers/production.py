from __future__ import annotations

from app.screening.rules import register_production_rules

from . import register_handler
from .individual_backtest import IndividualBacktestHandler, TASK_TYPE as INDIVIDUAL_BACKTEST_TASK_TYPE
from .market_daily_bars import MarketDailyBarsUpdateHandler, TASK_TYPE as MARKET_DAILY_BARS_TASK_TYPE
from .screening import ScreeningRuleExecuteHandler, TASK_TYPE as SCREENING_RULE_TASK_TYPE
from .stock_directory import StockDirectoryRefreshHandler, TASK_TYPE as STOCK_DIRECTORY_TASK_TYPE


def register_production_handlers() -> None:
    register_production_rules()
    register_handler(MARKET_DAILY_BARS_TASK_TYPE, MarketDailyBarsUpdateHandler())
    register_handler(STOCK_DIRECTORY_TASK_TYPE, StockDirectoryRefreshHandler())
    register_handler(SCREENING_RULE_TASK_TYPE, ScreeningRuleExecuteHandler())
    register_handler(INDIVIDUAL_BACKTEST_TASK_TYPE, IndividualBacktestHandler())
