"""公开敏感性分析模型与执行入口。"""

from importlib import import_module
from typing import Any

from .schema import (
    SensitivityAnalysisType,
    SensitivityCase,
    SensitivityParameters,
    SensitivitySettings,
)

__all__ = [
    "SensitivityAnalysisType",
    "SensitivityCase",
    "SensitivityParameters",
    "SensitivitySettings",
    "analyze_backtest_sensitivity",
]


def __getattr__(name: str) -> Any:
    if name != "analyze_backtest_sensitivity":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module("runtime.apps.sensitivity.api"), name)
    globals()[name] = value
    return value
