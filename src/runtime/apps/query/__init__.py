"""因子查询模型与按需加载的执行接口。"""

from importlib import import_module
from typing import Any

from .schema import Derivative, FactorQuery

LAZY_EXPORTS = {
    "QueryResult": ("runtime.apps.query.result", "QueryResult"),
    "build_query_table": ("runtime.apps.query.api", "build_query_table"),
    "execute_codes_query": ("runtime.apps.query.api", "execute_codes_query"),
    "execute_query": ("runtime.apps.query.api", "execute_query"),
}


def __getattr__(name: str) -> Any:
    if name not in LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
