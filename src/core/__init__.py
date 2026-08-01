"""Runtime 的公开模型与按需加载的执行接口。"""

from importlib import import_module
from typing import Any

from .apps.backtest.schema import BacktestParameters
from .apps.factor.schema import FactorAnalysisParameters
from .apps.query.schema import Derivative, FactorQuery

__version__ = "0.1.0"

LAZY_EXPORTS = {
    "PROD": ("core.config", "PROD"),
    "analyze_factors": ("core.apps.factor.api", "analyze_factors"),
    "execute_query": ("core.apps.query.api", "execute_query"),
    "run_backtest": ("core.apps.backtest.api", "run_backtest"),
}


def __getattr__(name: str) -> Any:
    if name not in LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
