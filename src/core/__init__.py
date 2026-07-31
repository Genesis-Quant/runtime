"""公开统一因子查询、分析与 DolphinDB 回测接口。"""

from .config import PROD

# isort: split

from .apps import (
    BacktestResult,
    Derivative,
    FactorAnalysisParameters,
    FactorAnalysisResult,
    FactorQuery,
    QueryResult,
    analyze_factors,
    execute_query,
    run_backtest,
)

__version__ = "0.1.0"

__all__ = [
    "PROD",
    "BacktestResult",
    "Derivative",
    "FactorAnalysisParameters",
    "FactorAnalysisResult",
    "FactorQuery",
    "QueryResult",
    "analyze_factors",
    "execute_query",
    "run_backtest",
]
