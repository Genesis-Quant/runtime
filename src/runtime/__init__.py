"""Runtime 的公开模型与按需加载的执行接口。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .apps.backtest.api import run_backtest
    from .apps.backtest.schema import BacktestParameters
    from .apps.factor.api import analyze_factors
    from .apps.factor.schema import FactorAnalysisParameters
    from .apps.query.api import execute_query
    from .apps.query.schema import Derivative, FactorQuery

__version__ = "0.1.0"

LAZY_EXPORTS = {
    "BacktestParameters": ("runtime.apps.backtest.schema", "BacktestParameters"),
    "Derivative": ("runtime.apps.query.schema", "Derivative"),
    "FactorAnalysisParameters": ("runtime.apps.factor.schema", "FactorAnalysisParameters"),
    "FactorQuery": ("runtime.apps.query.schema", "FactorQuery"),
    "analyze_factors": ("runtime.apps.factor.api", "analyze_factors"),
    "execute_query": ("runtime.apps.query.api", "execute_query"),
    "run_backtest": ("runtime.apps.backtest.api", "run_backtest"),
}

__all__ = [
    "BacktestParameters",
    "Derivative",
    "FactorAnalysisParameters",
    "FactorQuery",
    "analyze_factors",
    "execute_query",
    "run_backtest",
]


def __getattr__(name: str) -> Any:
    if name not in LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
