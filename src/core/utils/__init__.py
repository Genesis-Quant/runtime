"""统一导出数据层使用的日期、限流、重试、分页和 Tushare 对象。"""

from .dates import DateLike, normalize_date, normalize_date_range
from .logging import logger
from .paginate import Paginator
from .result import SessionResult
from .throttle import RateLimiter
from .retry import Retry
from .schema import (
    CODE_COLUMN,
    CORE_COLUMNS,
    FACTOR_COLUMN,
    IS_ST_FACTOR,
    TIME_COLUMN,
    VALUE_COLUMN,
    WEIGHT_PREFIX,
    index_weight_factor,
    normalize_factors,
)
from .ts_api import (
    INDUSTRY_TO_SECTOR,
    get_codes,
    get_pro,
    get_stock_metadata,
    get_trading_dates,
    pro,
    ts,
)


def __getattr__(name: str):
    """按需导出需要访问 Tushare 的股票元数据。"""
    if name in {"CODES", "CODE_TO_INDUSTRY", "STOCK_INDUSTRIES"}:
        from . import ts_api

        value = getattr(ts_api, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "CODES",
    "CODE_TO_INDUSTRY",
    "CODE_COLUMN",
    "CORE_COLUMNS",
    "DateLike",
    "FACTOR_COLUMN",
    "IS_ST_FACTOR",
    "INDUSTRY_TO_SECTOR",
    "Paginator",
    "RateLimiter",
    "Retry",
    "SessionResult",
    "TIME_COLUMN",
    "STOCK_INDUSTRIES",
    "VALUE_COLUMN",
    "WEIGHT_PREFIX",
    "get_codes",
    "get_pro",
    "get_stock_metadata",
    "get_trading_dates",
    "index_weight_factor",
    "logger",
    "normalize_date",
    "normalize_date_range",
    "normalize_factors",
    "pro",
    "ts",
]
