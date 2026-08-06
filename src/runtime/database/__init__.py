"""统一导出 DolphinDB 连接与长表写入能力。"""

from .session import create_session
from .tables import (
    CORE_TABLE,
    STOCK_DIVIDEND_COLUMNS,
    STOCK_DIVIDEND_EMPTY,
    STOCK_DIVIDEND_TABLE,
    CoreTableWriter,
    append_stock_dividends,
    ensure_stock_dividend_table,
    normalize_stock_dividends,
)

__all__ = [
    "CORE_TABLE",
    "CoreTableWriter",
    "STOCK_DIVIDEND_COLUMNS",
    "STOCK_DIVIDEND_EMPTY",
    "STOCK_DIVIDEND_TABLE",
    "append_stock_dividends",
    "create_session",
    "ensure_stock_dividend_table",
    "normalize_stock_dividends",
]
