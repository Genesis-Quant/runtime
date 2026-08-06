"""按需导出 Runtime 应用的参数模型。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .backtest.schema import BacktestParameters
    from .factor.schema import FactorAnalysisParameters
    from .query.schema import Derivative, FactorQuery

LAZY_EXPORTS = {
    "BacktestParameters": ("runtime.apps.backtest.schema", "BacktestParameters"),
    "Derivative": ("runtime.apps.query.schema", "Derivative"),
    "FactorAnalysisParameters": ("runtime.apps.factor.schema", "FactorAnalysisParameters"),
    "FactorQuery": ("runtime.apps.query.schema", "FactorQuery"),
}

__all__ = [
    "BacktestParameters",
    "Derivative",
    "FactorAnalysisParameters",
    "FactorQuery",
]


def __getattr__(name: str) -> Any:
    if name not in LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
