"""导出抽象任务层和每个固定数据接口的 Worker。"""

from functools import cache

from config import INDEX_CODES

from .base import BaseWorker, DateWorker, StockWorker
from .index_weight import IndexWeightWorker
from .stock_daily import (
    StockHfqWorker,
    StockLimitWorker,
    StockDailyWorker,
    StockAdjFactorWorker,
    StockDailyBasicWorker
)
from .stock_financial import (
    StockIncomeWorker,
    StockCashflowWorker,
    StockBalanceSheetWorker,
    StockFinaIndicatorWorker
)
from .stock_st import StockSTWorker


@cache
def available_factors() -> tuple[str, ...]:
    """返回全部固定 Worker 和配置指数 Worker 声明的 factor。"""
    workers = [
        StockDailyWorker(),
        StockLimitWorker(),
        StockDailyBasicWorker(),
        StockAdjFactorWorker(),
        StockHfqWorker(),
        StockSTWorker(),
        StockBalanceSheetWorker(),
        StockIncomeWorker(),
        StockCashflowWorker(),
        StockFinaIndicatorWorker(),
        *(IndexWeightWorker(index_code) for index_code in INDEX_CODES),
    ]
    return tuple(sorted({factor for worker in workers for factor in worker.factors}))


__all__ = [
    "BaseWorker",
    "DateWorker",
    "IndexWeightWorker",
    "StockAdjFactorWorker",
    "StockBalanceSheetWorker",
    "StockCashflowWorker",
    "StockDailyBasicWorker",
    "StockDailyWorker",
    "StockFinaIndicatorWorker",
    "StockHfqWorker",
    "StockIncomeWorker",
    "StockLimitWorker",
    "StockSTWorker",
    "StockWorker",
    "available_factors",
]
