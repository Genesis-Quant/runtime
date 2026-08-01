"""回测模型与按需加载的执行接口。"""

from importlib import import_module
from typing import Any

from .schema import BacktestParameters

LAZY_EXPORTS = {
    "BacktestResult": ("core.apps.backtest.result", "BacktestResult"),
    "run_backtest": ("core.apps.backtest.api", "run_backtest"),
}


def __getattr__(name: str) -> Any:
    if name not in LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
