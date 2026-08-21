"""参数调优模型与按需加载的执行接口。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from .schema import OptimizationAlgorithm, OptimizationParameters, OptimizationSettings

if TYPE_CHECKING:
    from .api import optimize_backtest

LAZY_EXPORTS = {
    "optimize_backtest": ("runtime.apps.optimization.api", "optimize_backtest"),
}

__all__ = ["OptimizationAlgorithm", "OptimizationParameters", "OptimizationSettings", "optimize_backtest"]


def __getattr__(name: str) -> Any:
    if name not in LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
