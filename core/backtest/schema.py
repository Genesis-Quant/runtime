"""定义回测执行结果。"""

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """保存一次已结束回测的标准输出。"""

    name: str
    message_rows: int
    trade_details: pd.DataFrame
    daily_positions: pd.DataFrame
    daily_portfolios: pd.DataFrame
    return_summary: pd.DataFrame
    daily_trading_statistics: pd.DataFrame
    engine_stat: pd.DataFrame
    context: Any


__all__ = ["BacktestResult"]
