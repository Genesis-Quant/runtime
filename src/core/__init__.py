"""公开统一因子查询与 DolphinDB 回测接口。"""

from .apps import (
    BacktestResult,
    Callback,
    Derivative,
    FactorQuery,
    QueryResult,
    Utility,
    build_query_table,
    execute_query,
    run_backtest,
)

__version__ = "0.1.0"

__all__ = [
    "BacktestResult",
    "Callback",
    "Derivative",
    "FactorQuery",
    "QueryResult",
    "Utility",
    "build_query_table",
    "execute_query",
    "run_backtest",
]
