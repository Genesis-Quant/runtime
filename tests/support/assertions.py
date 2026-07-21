"""比较 DolphinDB 输出与独立 Python 参考结果。"""

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd


def _series(value: Any) -> pd.Series:
    """把标量或向量结果规范化为无名称 Series。"""
    if isinstance(value, pd.Series):
        return value.reset_index(drop=True).rename(None)
    if isinstance(value, np.ndarray):
        return pd.Series(value).rename(None)
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return pd.Series(list(value)).rename(None)
    return pd.Series([value]).rename(None)


def assert_vector_equal(
    actual: Any,
    expected: Any,
    *,
    atol: float = 1e-9,
    rtol: float = 1e-9,
) -> None:
    """要求缺失位置完全一致，并按数据类型比较所有有效值。"""
    actual_series = _series(actual)
    expected_series = _series(expected)
    assert len(actual_series) == len(expected_series)

    actual_missing = actual_series.isna().to_numpy()
    expected_missing = expected_series.isna().to_numpy()
    np.testing.assert_array_equal(actual_missing, expected_missing)
    valid = ~actual_missing
    if not valid.any():
        return

    actual_values = actual_series.loc[valid]
    expected_values = expected_series.loc[valid]
    if pd.api.types.is_numeric_dtype(expected_values):
        np.testing.assert_allclose(
            actual_values.to_numpy(dtype=float),
            expected_values.to_numpy(dtype=float),
            atol=atol,
            rtol=rtol,
        )
        return
    if pd.api.types.is_datetime64_any_dtype(expected_values):
        np.testing.assert_array_equal(
            pd.to_datetime(actual_values).to_numpy(),
            pd.to_datetime(expected_values).to_numpy(),
        )
        return
    assert actual_values.tolist() == expected_values.tolist()


def assert_factor_frame(
    result: pd.DataFrame,
    source: pd.DataFrame,
    expected: dict[str, Any],
    *,
    atol: float = 1e-9,
    rtol: float = 1e-9,
) -> None:
    """验证执行器保持原行顺序，并逐因子比较参考结果。"""
    assert len(result) == len(source)
    for identity in ("time", "code"):
        if identity in source:
            assert_vector_equal(result[identity], source[identity])
    for name, values in expected.items():
        assert name in result
        assert_vector_equal(result[name], values, atol=atol, rtol=rtol)


__all__ = ["assert_factor_frame", "assert_vector_equal"]
