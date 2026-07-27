"""导出抽象任务层和每个固定数据接口的 Worker。"""

from functools import cache

from config import INDEX_CODES

from .base import BaseWorker, DateWorker, StockWorker, WideWorker
from .fund_daily import FUND_CODES, FundAdjFactorWorker, FundDailyWorker
from .index_weight import IndexWeightWorker
from .stock_daily import (
    StockAdjFactorWorker,
    StockDailyBasicWorker,
    StockDailyWorker,
    StockHfqWorker,
    StockLimitWorker,
)
from .stock_dividend import StockDividendWorker
from .stock_financial import (
    FINANCIAL_FACTORS,
    StockBalanceSheetWorker,
    StockCashflowWorker,
    StockFinaIndicatorWorker,
    StockIncomeWorker,
)
from .stock_st import StockSTWorker


@cache
def available_factors() -> tuple[str, ...]:
    """返回全部固定 Worker 和配置指数 Worker 声明的 factor。"""
    workers = [
        FundAdjFactorWorker(),
        FundDailyWorker(),
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
    "FINANCIAL_FACTORS",
    "FUND_CODES",
    "BaseWorker",
    "DateWorker",
    "FundAdjFactorWorker",
    "FundDailyWorker",
    "IndexWeightWorker",
    "StockAdjFactorWorker",
    "StockBalanceSheetWorker",
    "StockCashflowWorker",
    "StockDailyBasicWorker",
    "StockDailyWorker",
    "StockDividendWorker",
    "StockFinaIndicatorWorker",
    "StockHfqWorker",
    "StockIncomeWorker",
    "StockLimitWorker",
    "StockSTWorker",
    "StockWorker",
    "WideWorker",
    "available_factors",
]
