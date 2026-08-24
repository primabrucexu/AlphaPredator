from __future__ import annotations

from . import register_handler
from .jygs import JygsLimitUpSyncHandler, TASK_TYPE as JYGS_TASK_TYPE
from .market_daily_bars import MarketDailyBarsUpdateHandler, TASK_TYPE as MARKET_DAILY_BARS_TASK_TYPE
from .stock_directory import StockDirectoryRefreshHandler, TASK_TYPE as STOCK_DIRECTORY_TASK_TYPE


def register_production_handlers() -> None:
    register_handler(JYGS_TASK_TYPE, JygsLimitUpSyncHandler())
    register_handler(MARKET_DAILY_BARS_TASK_TYPE, MarketDailyBarsUpdateHandler())
    register_handler(STOCK_DIRECTORY_TASK_TYPE, StockDirectoryRefreshHandler())
