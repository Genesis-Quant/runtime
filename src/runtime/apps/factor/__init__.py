"""因子分析模型与按需加载的执行接口。"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from .schema import FactorAnalysisParameters

if TYPE_CHECKING:
    from .api import analyze_factors

LAZY_EXPORTS = {
    "analyze_factors": ("runtime.apps.factor.api", "analyze_factors"),
}

__all__ = ["FactorAnalysisParameters", "analyze_factors"]


def __getattr__(name: str) -> Any:
    if name not in LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
