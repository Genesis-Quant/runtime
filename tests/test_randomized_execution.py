"""使用 Hypothesis 随机差分验证 DIRECT、TS 与 CS 的组合语义。"""

from typing import Any

from hypothesis import given, strategies as st
import numpy as np
import pandas as pd

from tests.support.assertions import assert_vector_equal
from tests.support.dsl import compute_factors, cross_section, direct, time_series
from tests.support.panel import apply_cross_section, apply_time_series, neutralize, zscore


FINITE = st.floats(
    min_value=-500.0,
    max_value=500.0,
    allow_nan=False,
    allow_infinity=False,
    width=32,
)


@st.composite
def numeric_rows(draw: st.DrawFn) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """生成三列含随机 NULL 和零值的等长有限浮点向量。"""
    size = draw(st.integers(min_value=10, max_value=40))
    values: list[np.ndarray] = []
    for index in range(3):
        strategy = st.one_of(st.just(0.0), FINITE) if index == 1 else FINITE
        current = np.asarray(
            draw(st.lists(strategy, min_size=size, max_size=size)),
            dtype=float,
        )
        missing = draw(st.lists(st.booleans(), min_size=size, max_size=size))
        current[np.asarray(missing) & (np.arange(size) % 4 == index)] = np.nan
        values.append(current)
    return values[0], values[1], values[2]


@given(rows=numeric_rows())
def test_random_direct_arithmetic_matches_numpy(ddb_session: Any, rows) -> None:
    """随机核对成对算术、安全除法及横向缺失值聚合。"""
    left, right, third = rows
    source = pd.DataFrame({"left": left, "right": right, "third": third})
    definitions = {
        "add": direct("binary.add", {"left": "left", "right": "right"}),
        "sub": direct("binary.sub", {"left": "left", "right": "right"}),
        "mul": direct("binary.mul", {"left": "left", "right": "right"}),
        "div": direct("binary.div", {"left": "left", "right": "right"}),
        "floor_div": direct("binary.floor_div", {"left": "left", "right": "right"}),
        "mod": direct("binary.mod", {"left": "left", "right": "right"}),
        "mean": direct("multiary.mean", {"cols": ["left", "right", "third"]}),
        "std0": direct("multiary.std", {"cols": ["left", "right", "third"]}, {"ddof": 0}),
        "std1": direct("multiary.std", {"cols": ["left", "right", "third"]}, {"ddof": 1}),
    }
    valid_pair = np.isfinite(left) & np.isfinite(right)
    valid_divisor = valid_pair & (right != 0)
    expected: dict[str, Any] = {
        "add": np.where(valid_pair, left + right, np.nan),
        "sub": np.where(valid_pair, left - right, np.nan),
        "mul": np.where(valid_pair, left * right, np.nan),
        "mean": source.mean(axis=1, skipna=True),
        "std0": source.std(axis=1, skipna=True, ddof=0),
        "std1": source.std(axis=1, skipna=True, ddof=1),
    }
    with np.errstate(divide="ignore", invalid="ignore"):
        quotient = np.where(valid_divisor, left / right, np.nan)
        expected["div"] = quotient
        expected["floor_div"] = np.floor(quotient)
        expected["mod"] = np.where(valid_divisor, left - np.floor(left / right) * right, np.nan)

    result = compute_factors(ddb_session, source, definitions)
    for name, values in expected.items():
        assert_vector_equal(result[name], values, atol=1e-8, rtol=1e-8)


@st.composite
def time_series_rows(draw: st.DrawFn) -> tuple[np.ndarray, np.ndarray]:
    """生成三只股票各十二期的随机数值和资格掩码。"""
    size = 36
    values = np.asarray(
        draw(st.lists(FINITE, min_size=size, max_size=size)),
        dtype=float,
    )
    missing = np.asarray(
        draw(st.lists(st.booleans(), min_size=size, max_size=size)),
        dtype=bool,
    )
    values[missing & (np.arange(size) % 3 == 0)] = np.nan
    active = np.asarray(
        draw(st.lists(st.booleans(), min_size=size, max_size=size)),
        dtype=bool,
    )
    return values, active


@given(rows=time_series_rows())
def test_random_time_series_respects_code_time_and_on(ddb_session: Any, rows) -> None:
    """随机核对乱序多股票数据中的筛选、排序、窗口和回填。"""
    values, active = rows
    source = pd.DataFrame(
        {
            "time": list(pd.date_range("2022-01-03", periods=12, freq="B")) * 3,
            "code": np.repeat(["A", "B", "C"], 12),
            "value": values,
            "active": active,
        }
    )
    order = np.random.default_rng(9917).permutation(len(source))
    source = source.iloc[order].reset_index(drop=True)
    definitions = {
        "diff": time_series("unary.diff", {"col": "value"}, {"periods": 1}, on="active"),
        "mean": time_series("unary.rolling_mean", {"col": "value"}, {"window": 4, "min_periods": 2}, on="active"),
        "cumulative": time_series("unary.cum_mean", {"col": "value"}, {"min_periods": 2}, on="active"),
        "zscore": time_series("unary.rolling_zscore", {"col": "value"}, {"window": 4, "min_periods": 2}, on="active"),
    }
    expected_diff = apply_time_series(
        source,
        source["active"],
        lambda group: group["value"] - group["value"].shift(1),
    )
    expected_mean = apply_time_series(
        source,
        source["active"],
        lambda group: group["value"].rolling(4, min_periods=2).mean(),
    )
    expected_cumulative = apply_time_series(
        source,
        source["active"],
        lambda group: group["value"].expanding(min_periods=2).mean(),
    )

    def rolling_zscore(group: pd.DataFrame) -> pd.Series:
        """计算当前值相对四期样本均值和样本标准差的 z-score。"""
        rolling = group["value"].rolling(4, min_periods=2)
        scale = rolling.std(ddof=1)
        result = (group["value"] - rolling.mean()) / scale
        return result.mask(scale == 0)

    expected_zscore = apply_time_series(
        source,
        source["active"],
        rolling_zscore,
    )
    result = compute_factors(ddb_session, source, definitions)
    assert_vector_equal(result["diff"], expected_diff)
    assert_vector_equal(result["mean"], expected_mean)
    assert_vector_equal(result["cumulative"], expected_cumulative)
    assert_vector_equal(result["zscore"], expected_zscore, atol=1e-8, rtol=1e-8)


@st.composite
def cross_section_rows(draw: st.DrawFn) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """生成四个日期、每期十只股票的随机截面输入。"""
    size = 40
    target = np.asarray(
        draw(st.lists(FINITE, min_size=size, max_size=size)),
        dtype=float,
    )
    missing = np.asarray(
        draw(st.lists(st.booleans(), min_size=size, max_size=size)),
        dtype=bool,
    )
    target[missing & (np.arange(size) % 4 == 0)] = np.nan
    size_control = np.asarray(
        draw(
            st.lists(
                st.floats(
                    min_value=1.0,
                    max_value=1000.0,
                    allow_nan=False,
                    allow_infinity=False,
                    width=32,
                ),
                min_size=size,
                max_size=size,
            )
        ),
        dtype=float,
    )
    active = np.asarray(
        draw(st.lists(st.booleans(), min_size=size, max_size=size)),
        dtype=bool,
    )
    return target, size_control, active


@given(rows=cross_section_rows())
def test_random_cross_sections_match_pandas_and_numpy(ddb_session: Any, rows) -> None:
    """随机核对截面排名、分位数、缩尾、标准化与混合控制 OLS。"""
    target, size_control, active = rows
    source = pd.DataFrame(
        {
            "time": np.repeat(pd.date_range("2023-04-03", periods=4, freq="B"), 10),
            "code": [f"S{index:02d}" for index in range(10)] * 4,
            "target": target,
            "size": size_control,
            "industry": (["bank", "energy", "tech", "bank", "tech"] * 2) * 4,
            "active": active,
        }
    )
    order = np.random.default_rng(202304).permutation(len(source))
    source = source.iloc[order].reset_index(drop=True)
    definitions = {
        "demean": cross_section("unary.demean", {"col": "target"}, on="active"),
        "zscore": cross_section("unary.zscore", {"col": "target"}, {"ddof": 0}, on="active"),
        "rank": cross_section("unary.rank", {"col": "target"}, {"ascending": False, "ties_method": "average"}, on="active"),
        "quantile": cross_section("unary.quantile", {"col": "target"}, {"q": 0.3}, on="active"),
        "winsor": cross_section("unary.winsorize", {"col": "target"}, {"lower": 0.1, "upper": 0.9}, on="active"),
        "neutral": cross_section("controls.neutralize_by", {"target": "target", "controls": ["industry", "size"]}, {"intercept": True}, on="active"),
    }
    expected_demean = apply_cross_section(
        source,
        source["active"],
        lambda group: group["target"] - group["target"].mean(),
    )
    expected_zscore = apply_cross_section(
        source,
        source["active"],
        lambda group: zscore(group["target"], ddof=0),
    )
    expected_rank = apply_cross_section(
        source,
        source["active"],
        lambda group: group["target"].rank(method="average", ascending=False),
    )
    expected_quantile = apply_cross_section(
        source,
        source["active"],
        lambda group: [group["target"].quantile(0.3)] * len(group),
    )

    def winsorize(group: pd.DataFrame) -> pd.Series:
        """按线性分位数边界缩尾并保留原 NULL。"""
        low = group["target"].quantile(0.1)
        high = group["target"].quantile(0.9)
        return group["target"].clip(low, high)

    expected_winsor = apply_cross_section(
        source,
        source["active"],
        winsorize,
    )
    expected_neutral = apply_cross_section(
        source,
        source["active"],
        lambda group: neutralize(
            group["target"],
            group[["industry", "size"]],
            intercept=True,
        ),
    )
    result = compute_factors(ddb_session, source, definitions)
    assert_vector_equal(result["demean"], expected_demean)
    assert_vector_equal(result["zscore"], expected_zscore, atol=1e-8, rtol=1e-8)
    assert_vector_equal(result["rank"], expected_rank)
    assert_vector_equal(result["quantile"], expected_quantile, atol=1e-8, rtol=1e-8)
    assert_vector_equal(result["winsor"], expected_winsor, atol=1e-8, rtol=1e-8)
    assert_vector_equal(result["neutral"], expected_neutral, atol=1e-7, rtol=1e-7)
