"""独立实现 DSL 的筛选、分组、排序和回填语义。"""

from collections.abc import Callable, Iterable
from typing import Any

import numpy as np
import pandas as pd


def bool_mask(value: pd.Series | Iterable[bool], index: pd.Index) -> pd.Series:
    """把 NULL 按 false 处理并生成与输入索引一致的布尔掩码。"""
    return pd.Series(value, index=index).astype("boolean").fillna(False).astype(bool)


def apply_time_series(
    source: pd.DataFrame,
    on: pd.Series | Iterable[bool],
    calculator: Callable[[pd.DataFrame], Iterable[Any]],
    *,
    dtype: str | type = "float64",
) -> pd.Series:
    """先按 on 筛选，再按 code/time 计算，并把结果恢复到原始行。"""
    result = pd.Series(np.nan, index=source.index, dtype=dtype)
    selected = source.loc[bool_mask(on, source.index)].sort_values(
        ["code", "time"],
        kind="stable",
    )
    for _, group in selected.groupby("code", sort=False):
        values = list(calculator(group))
        assert len(values) == len(group)
        result.loc[group.index] = values
    return result


def apply_cross_section(
    source: pd.DataFrame,
    on: pd.Series | Iterable[bool],
    calculator: Callable[[pd.DataFrame], Iterable[Any]],
    *,
    by: str | None = None,
    dtype: str | type = "float64",
) -> pd.Series:
    """按 on 筛选后逐交易日或逐交易日分类组计算并回填。"""
    result = pd.Series(np.nan, index=source.index, dtype=dtype)
    mask = bool_mask(on, source.index)
    if by is not None:
        mask &= source[by].notna()
    selected = source.loc[mask]
    keys: str | list[str] = "time" if by is None else ["time", by]
    for _, group in selected.groupby(keys, sort=False, dropna=False):
        values = list(calculator(group))
        assert len(values) == len(group)
        result.loc[group.index] = values
    return result


def zscore(values: pd.Series, ddof: int) -> pd.Series:
    """忽略 NULL 计算 z-score，零方差或样本不足时返回全 NULL。"""
    scale = values.std(ddof=ddof)
    if pd.isna(scale) or scale == 0:
        return pd.Series(np.nan, index=values.index)
    return (values - values.mean()) / scale


def neutralize(
    target: pd.Series,
    controls: pd.DataFrame,
    *,
    intercept: bool,
) -> pd.Series:
    """使用 numpy OLS 复刻分类展开、常量删除和样本不足退化规则。"""
    valid = pd.Series(np.isfinite(target.to_numpy(dtype=float)), index=target.index)
    categories: list[str] = []
    for name, values in controls.items():
        categorical = (
            isinstance(values.dtype, pd.CategoricalDtype)
            or pd.api.types.is_bool_dtype(values)
            or pd.api.types.is_object_dtype(values)
            or pd.api.types.is_string_dtype(values)
        )
        if categorical:
            categories.append(name)
            valid &= values.notna()
        else:
            valid &= np.isfinite(values.to_numpy(dtype=float))

    result = pd.Series(np.nan, index=target.index, dtype="float64")
    if not valid.any():
        return result
    y = target.loc[valid].astype(float)
    encoded = pd.get_dummies(
        controls.loc[valid],
        columns=categories,
        drop_first=True,
        dtype=float,
    ).astype(float)
    encoded = encoded.loc[:, encoded.nunique(dropna=False) > 1]
    parameter_count = encoded.shape[1] + int(intercept)
    if len(y) <= 1 or encoded.empty or len(y) <= parameter_count:
        result.loc[valid] = y - y.mean()
        return result

    design = encoded.to_numpy(dtype=float)
    if intercept:
        design = np.column_stack([np.ones(len(design)), design])
    coefficients = np.linalg.lstsq(design, y.to_numpy(), rcond=None)[0]
    result.loc[valid] = y.to_numpy() - design @ coefficients
    return result


__all__ = [
    "apply_cross_section",
    "apply_time_series",
    "bool_mask",
    "neutralize",
    "zscore",
]
