"""使用 Python 独立结果验证所有 DolphinDB 公共函数。"""

import numpy as np
import pandas as pd
import pytest
import talib

from tests.support.assertions import assert_vector_equal
from tests.support.dsl import run_uploaded


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1", [True, False, False, False]),
        ("1.5", [True, False, False, False]),
        ('"text"', [True, False, False, False]),
        ("true", [True, False, False, False]),
        ("2024.02.29", [True, False, False, False]),
        ("1 2", [False, True, False, False]),
        ("double([])", [False, True, False, False]),
        ('["a", "b"]', [False, True, False, False]),
        ("`bank`tech", [False, True, False, False]),
        ("matrix(1 2, 3 4)", [False, False, False, False]),
        ("dict(STRING, ANY)", [False, False, True, False]),
        ("table(1 2 as value)", [False, False, False, True]),
    ],
)
def test_form_predicates_distinguish_all_supported_shapes(
    ddb_session,
    expression: str,
    expected: list[bool],
) -> None:
    """四个形态函数分别核对十二种标量、向量及复合对象。"""
    result = ddb_session.run(
        f"""
(
    is_scalar_form({expression}),
    is_vector_form({expression}),
    is_dictionary_form({expression}),
    is_table_form({expression})
)
"""
    )
    assert result == expected


def test_is_finite_number_rejects_every_non_finite_value(ddb_session) -> None:
    """NULL、NaN 和正负无穷都不是有限数。"""
    values = np.array([1.0, -2.5, np.nan, np.inf, -np.inf, 0.0])
    actual = run_uploaded(ddb_session, "is_finite_number(finite_input)", finite_input=values)
    assert_vector_equal(actual, [True, True, False, False, False, True])
    integer_actual = run_uploaded(
        ddb_session,
        "is_finite_number(integer_input)",
        integer_input=np.array([-3, -1, 0, 1, 5], dtype=np.int64),
    )
    assert_vector_equal(integer_actual, [True] * 5)


def test_divide_or_null_matches_numpy_safe_division(ddb_session) -> None:
    """分母为零或缺失时返回 NULL，其余位置执行普通除法。"""
    left = np.array(
        [6.0, 8.0, np.nan, 5.0, -4.0, -5.0, 0.0, 9.0, 1e12, -1e12, 7.0, -7.0]
    )
    right = np.array(
        [2.0, 0.0, 2.0, np.nan, -2.0, 2.0, -3.0, -3.0, 1e-6, -1e-6, 0.5, -0.5]
    )
    actual = run_uploaded(
        ddb_session,
        "divide_or_null(divide_left, divide_right)",
        divide_left=left,
        divide_right=right,
    )
    expected = np.full(len(left), np.nan)
    valid = np.isfinite(left) & np.isfinite(right) & (right != 0)
    expected[valid] = left[valid] / right[valid]
    assert_vector_equal(actual, expected)


def test_floor_as_double_avoids_long_overflow(ddb_session) -> None:
    """浮点向下取整在 LONG 范围外仍保留有限 DOUBLE，而不是变为 NULL。"""
    values = np.array(
        [
            -1e30,
            -1e20,
            -9_007_199_254_740_992.0,
            -2.9,
            -2.0,
            -0.1,
            0.0,
            0.1,
            2.0,
            2.9,
            9_007_199_254_740_992.0,
            1e20,
            1e30,
            np.nan,
        ]
    )
    actual = run_uploaded(
        ddb_session,
        "floor_as_double(floor_input)",
        floor_input=values,
    )
    assert_vector_equal(actual, np.floor(values))


@pytest.mark.parametrize("ma_type", [0, 1, 2, 3, 4, 5, 6, 8])
@pytest.mark.parametrize("time_period", [3, 8])
def test_talib_moving_average_matches_standard_ma_type(
    ddb_session,
    ma_type: int,
    time_period: int,
) -> None:
    """用十六组类型和周期核对 TA-Lib 均线，T3 默认 vfactor 为 0.7。"""
    position = np.arange(180, dtype=float)
    values = 30.0 + 0.05 * position + np.sin(position / 7.0)
    actual = run_uploaded(
        ddb_session,
        f"talib_moving_average(ma_input, {time_period}, {ma_type})",
        ma_input=values,
    )
    expected = talib.MA(values, timeperiod=time_period, matype=ma_type)
    assert_vector_equal(actual, expected, atol=1e-8, rtol=1e-9)


@pytest.mark.parametrize(
    ("expression", "expected", "expected_type"),
    [
        ('cast_value(1 0, "bool")', [True, False], "FAST BOOL VECTOR"),
        ('cast_value(1.9 -2.1, "int")', [2, -2], "FAST INT VECTOR"),
        ('cast_value(1 2, "long")', [1, 2], "FAST LONG VECTOR"),
        ('cast_value(1 2, "float")', [1.0, 2.0], "FAST FLOAT VECTOR"),
        ('cast_value(1 2, "double")', [1.0, 2.0], "FAST DOUBLE VECTOR"),
        ('cast_value(1 2, "string")', ["1", "2"], "STRING VECTOR"),
        ('cast_value("bank", "symbol")', ["bank"], "FAST SYMBOL VECTOR"),
        ('cast_value(["bank", "tech"], "symbol")', ["bank", "tech"], "FAST SYMBOL VECTOR"),
        ('cast_value("2024-02-29", "date")', [pd.Timestamp("2024-02-29")], "DATE"),
        (
            'cast_value(["2024-02-28", "2024-02-29"], "date")',
            [pd.Timestamp("2024-02-28"), pd.Timestamp("2024-02-29")],
            "FAST DATE VECTOR",
        ),
        ('cast_value(2024.02.29, "date")', [pd.Timestamp("2024-02-29")], "DATE"),
        (
            'cast_value("2024-02-29T09:30:00", "timestamp")',
            [pd.Timestamp("2024-02-29 09:30:00")],
            "TIMESTAMP",
        ),
        (
            'cast_value("2024-02-29T09:30:00.123", "timestamp")',
            [pd.Timestamp("2024-02-29 09:30:00.123")],
            "TIMESTAMP",
        ),
        (
            'cast_value(["2024-02-29T09:30:00", "2024-03-01T10:00:00"], "timestamp")',
            [pd.Timestamp("2024-02-29 09:30:00"), pd.Timestamp("2024-03-01 10:00:00")],
            "FAST TIMESTAMP VECTOR",
        ),
        (
            'cast_value(2024.02.29T09:30:00.000, "timestamp")',
            [pd.Timestamp("2024-02-29 09:30:00")],
            "TIMESTAMP",
        ),
    ],
)
def test_cast_value_converts_values_and_types(
    ddb_session,
    expression: str,
    expected: list[object],
    expected_type: str,
) -> None:
    """每种受支持 dtype 都必须同时得到正确值和 DolphinDB 类型。"""
    actual = ddb_session.run(expression)
    type_name = ddb_session.run(f"typestr({expression})")
    assert_vector_equal(actual, expected)
    assert type_name == expected_type


def test_cast_value_rejects_unknown_dtype(ddb_session) -> None:
    """未知 dtype 应返回明确错误。"""
    with pytest.raises(RuntimeError, match="不支持转换为 dtype=decimal"):
        ddb_session.run('cast_value(1, "decimal")')


@pytest.mark.parametrize(
    ("value", "reference", "expected"),
    [
        ("7", "1 2 3 4", [7, 7, 7, 7]),
        ("-2.5", "double([1, 2, 3])", [-2.5, -2.5, -2.5]),
        ("true", "bool([true, false, NULL])", [True, True, True]),
        ("false", "1..5", [False] * 5),
        ('"bank"', '["a", "b"]', ["bank", "bank"]),
        ("`bank", "`a`b`c", ["bank", "bank", "bank"]),
        (
            "2024.02.29",
            "date([2024.01.01, 2024.01.02])",
            [pd.Timestamp("2024-02-29")] * 2,
        ),
        (
            "2024.02.29T09:30:00.000",
            "timestamp([2024.01.01T00:00:00.000, 2024.01.02T00:00:00.000])",
            [pd.Timestamp("2024-02-29 09:30:00")] * 2,
        ),
        ("double(NULL)", "1 2 3", [np.nan] * 3),
        ("42", "int([])", []),
    ],
)
def test_broadcast_like_matches_reference_length(
    ddb_session,
    value: str,
    reference: str,
    expected: list[object],
) -> None:
    """十种数值、逻辑、文本、时间及空向量广播均保持参考长度。"""
    assert_vector_equal(
        ddb_session.run(f"broadcast_like({value}, {reference})"),
        expected,
    )


@pytest.mark.parametrize("ascending", [True, False])
@pytest.mark.parametrize("method", ["min", "max", "average", "first", "dense"])
@pytest.mark.parametrize("percent", [True, False])
def test_cross_section_rank_matches_pandas(
    ddb_session,
    ascending: bool,
    method: str,
    percent: bool,
) -> None:
    """所有并列规则、方向和百分位组合都应与 pandas 一致。"""
    values = pd.Series([3.0, 1.0, 1.0, np.nan, 2.0, 3.0])
    actual = run_uploaded(
        ddb_session,
        f'cross_section_rank(rank_values, {str(ascending).lower()}, "{method}", {str(percent).lower()})',
        rank_values=values.to_numpy(),
    )
    expected = values.rank(
        method=method,
        ascending=ascending,
        pct=percent,
        na_option="keep",
    )
    assert_vector_equal(actual, expected)


def _slope(left: np.ndarray, right: np.ndarray) -> float:
    """使用成对有效样本计算带截距 OLS 斜率。"""
    valid = np.isfinite(left) & np.isfinite(right)
    x = left[valid]
    y = right[valid]
    if len(x) < 2 or np.var(x) == 0:
        return np.nan
    return float(np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1))


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ([1.0, 2.0, 3.0, 4.0], [3.0, 5.0, 7.0, 9.0]),
        ([1.0, 2.0, 3.0, 4.0], [10.0, 8.0, 6.0, 4.0]),
        ([0.0, 1.0, 2.0, 3.0, 4.0, 5.0], [1.0, 1.0, 4.0, 5.0, 7.0, 11.0]),
        ([1.0, 2.0, np.nan, 4.0], [3.0, np.nan, 7.0, 10.0]),
        ([1.0, 2.0, 3.0, 4.0], [3.0, np.nan, 7.0, 9.0]),
        ([1.0, np.nan, 3.0, 4.0], [np.nan, 5.0, 7.0, 9.0]),
        ([2.0, 2.0, 2.0, 2.0], [1.0, 3.0, 2.0, 8.0]),
        ([1.0, np.nan, np.nan], [2.0, 4.0, np.nan]),
        ([np.nan, np.nan], [1.0, 2.0]),
        ([1.0, 4.0, np.nan], [3.0, 9.0, 12.0]),
    ],
)
def test_cross_section_slope_matches_numpy(
    ddb_session,
    left: list[float],
    right: list[float],
) -> None:
    """截面斜率应使用成对有效样本，常量或空自变量返回 NULL。"""
    left_array = np.asarray(left)
    right_array = np.asarray(right)
    actual = run_uploaded(
        ddb_session,
        "cross_section_slope(slope_left, slope_right)",
        slope_left=left_array,
        slope_right=right_array,
    )
    assert_vector_equal(actual, [_slope(left_array, right_array)])


@pytest.mark.parametrize(
    ("window", "minimum", "expected"),
    [
        (1, None, 1),
        (5, None, 5),
        (10, None, 10),
        (5, 1, 1),
        (5, 2, 2),
        (5, 5, 5),
        (20, 3, 3),
        (2, 1, 1),
        (12, 7, 7),
        (100, 64, 64),
    ],
)
def test_rolling_min_periods_resolves_null_and_explicit_values(
    ddb_session,
    window: int,
    minimum: int | None,
    expected: int,
) -> None:
    """十种窗口边界下，NULL 使用完整窗口，显式值保持不变。"""
    expression = "int(NULL)" if minimum is None else str(minimum)
    assert ddb_session.run(f"rolling_min_periods({window}, {expression})") == expected


def test_expanding_masks_count_single_and_paired_valid_observations(ddb_session) -> None:
    """累计结果只在单列或双列有效样本数达到阈值后暴露。"""
    result = np.arange(1.0, 13.0)
    value = np.array(
        [1.0, np.nan, 3.0, 4.0, np.nan, 6.0, 7.0, np.nan, 9.0, 10.0, 11.0, np.nan]
    )
    actual = run_uploaded(
        ddb_session,
        "mask_expanding_result(mask_result, mask_value, 3)",
        mask_result=result,
        mask_value=value,
    )
    assert_vector_equal(
        actual,
        [np.nan, np.nan, np.nan, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0],
    )

    left = np.array(
        [1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0, np.nan, 9.0, 10.0, 11.0, 12.0]
    )
    right = np.array(
        [1.0, np.nan, 3.0, 4.0, 5.0, np.nan, 7.0, 8.0, 9.0, 10.0, np.nan, 12.0]
    )
    actual_pair = run_uploaded(
        ddb_session,
        "mask_pair_expanding_result(mask_result, mask_left, mask_right, 3)",
        mask_result=result,
        mask_left=left,
        mask_right=right,
    )
    assert_vector_equal(
        actual_pair,
        [np.nan, np.nan, np.nan, np.nan, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0],
    )


def _rolling_regression(
    left: np.ndarray,
    right: np.ndarray,
    window: int,
    minimum: int,
) -> tuple[np.ndarray, np.ndarray]:
    """按行计算滚动 OLS 斜率和截距。"""
    slope = np.full(len(left), np.nan)
    intercept = np.full(len(left), np.nan)
    for position in range(len(left)):
        start = max(0, position - window + 1)
        x = left[start : position + 1]
        y = right[start : position + 1]
        valid = np.isfinite(x) & np.isfinite(y)
        if valid.sum() < minimum or np.var(x[valid]) == 0:
            continue
        design = np.column_stack([np.ones(valid.sum()), x[valid]])
        intercept[position], slope[position] = np.linalg.lstsq(
            design,
            y[valid],
            rcond=None,
        )[0]
    return slope, intercept


def test_rolling_regression_helpers_use_pairwise_valid_samples(ddb_session) -> None:
    """滚动斜率和截距在单侧缺失时仍应使用完全相同的成对样本。"""
    left = np.array(
        [1.0, 2.0, 3.0, 4.0, np.nan, 6.0, 7.0, 8.0, 9.0, 10.0, np.nan, 12.0, 13.0, 14.0]
    )
    right = np.array(
        [2.0, 4.5, np.nan, 8.0, 10.0, 12.5, 14.0, 16.5, 18.0, 20.5, 22.0, 24.0, 26.5, np.nan]
    )
    expected_slope, expected_intercept = _rolling_regression(left, right, 4, 2)
    actual_slope = run_uploaded(
        ddb_session,
        "rolling_slope(reg_left, reg_right, 4, 2)",
        reg_left=left,
        reg_right=right,
    )
    actual_intercept = ddb_session.run(
        "rolling_intercept(reg_left, reg_right, 4, 2)"
    )
    assert_vector_equal(actual_slope, expected_slope)
    assert_vector_equal(actual_intercept, expected_intercept)


def test_rolling_true_count_treats_null_as_false(ddb_session) -> None:
    """布尔滚动计数应把 NULL 当作 false，并按行数应用最少窗口。"""
    actual = ddb_session.run(
        "value=true NULL false true true NULL false true false true NULL true; "
        "rolling_true_count(value, 4, 3)"
    )
    values = pd.Series(
        [True, None, False, True, True, None, False, True, False, True, None, True],
        dtype="boolean",
    )
    expected = values.fillna(False).astype(int).rolling(4, min_periods=3).sum()
    assert_vector_equal(actual, expected)
