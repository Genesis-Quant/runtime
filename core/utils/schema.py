"""定义统一因子数据的列契约和 factor 命名规则。"""

from collections.abc import Iterable
import re

TIME_COLUMN = "time"
CODE_COLUMN = "code"
FACTOR_COLUMN = "factor"
VALUE_COLUMN = "value"
CORE_COLUMNS = (
    TIME_COLUMN,
    CODE_COLUMN,
    FACTOR_COLUMN,
    VALUE_COLUMN,
)
IS_ST_FACTOR = "is_st"
WEIGHT_PREFIX = "weight_"


def index_weight_factor(index_code: str) -> str:
    """把指数代码转换为统一长表中的权重 factor 名。"""
    normalized = str(index_code).strip().upper()
    if re.fullmatch(r"[A-Z0-9]+\.[A-Z0-9]+", normalized) is None:
        raise ValueError(f"无效指数代码：{index_code!r}")
    return WEIGHT_PREFIX + normalized.replace(".", "")


def normalize_factors(values: Iterable[str]) -> list[str]:
    """清理、去重并校验 factor 列表。"""
    factors: list[str] = []
    for value in values:
        if value is None:
            continue
        factor = str(value).strip()
        if not factor:
            continue
        if factor not in factors:
            factors.append(factor)
    if not factors:
        raise ValueError("factor 至少包含一个非空值")
    return factors


__all__ = [
    "CODE_COLUMN",
    "CORE_COLUMNS",
    "FACTOR_COLUMN",
    "IS_ST_FACTOR",
    "TIME_COLUMN",
    "VALUE_COLUMN",
    "WEIGHT_PREFIX",
    "index_weight_factor",
    "normalize_factors",
]
