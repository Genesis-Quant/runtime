"""使用 Pandas/NumPy 独立结果验证非 TA-Lib 时序算符。"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import pytest

from core.operators import Derivative
from core.operators.base import TimeSeriesOperator
from tests.support.assertions import assert_vector_equal
from tests.support.dsl import TRUE_NODE, compute_factors, time_series


@dataclass(frozen=True)
class TimeSeriesContract:
    """保存一个时序算符的完整 DSL 与独立期望结果。"""

    definition: dict[str, object]
    expected: object


def _ts(
    operation: str,
    fields: dict[str, object],
    params: dict[str, object] | None = None,
) -> dict[str, object]:
    """构造对全部输入行启用的 TS 节点。"""
    return time_series(operation, fields, params, on=TRUE_NODE)


def _expanding_aggregate(
    values: pd.Series,
    minimum: int,
    method: str,
) -> pd.Series:
    """按跳过 NULL 且 NULL 当前行仍可输出累计值的语义计算累计统计。"""
    result = np.full(len(values), np.nan)
    for position in range(len(values)):
        valid = values.iloc[: position + 1].dropna()
        if len(valid) < minimum:
            continue
        if method == "count":
            result[position] = len(valid)
        elif method == "sum":
            result[position] = valid.sum()
        elif method == "prod":
            result[position] = valid.prod()
        elif method == "min":
            result[position] = valid.min()
        elif method == "max":
            result[position] = valid.max()
        elif method == "mean":
            result[position] = valid.mean()
        else:
            raise AssertionError(f"未知累计方法 {method}")
    return pd.Series(result)


def _current_rank(
    values: pd.Series,
    *,
    window: int | None,
    minimum: int,
    ascending: bool,
    method: str,
    percent: bool,
) -> pd.Series:
    """计算当前位置在滚动或扩展窗口内的排名。"""
    result = np.full(len(values), np.nan)
    for position in range(len(values)):
        start = 0 if window is None else max(0, position - window + 1)
        sample = values.iloc[start : position + 1]
        if sample.notna().sum() < minimum or pd.isna(values.iloc[position]):
            continue
        ranks = sample.rank(
            method=method,
            ascending=ascending,
            pct=percent,
            na_option="keep",
        )
        result[position] = ranks.iloc[-1]
    return pd.Series(result)


def _rolling_endpoint(
    values: pd.Series,
    window: int,
    minimum: int,
    *,
    first: bool,
) -> pd.Series:
    """满足有效样本门槛后返回窗口物理首端或末端值。"""
    result = np.full(len(values), np.nan)
    for position in range(len(values)):
        start = max(0, position - window + 1)
        sample = values.iloc[start : position + 1]
        if sample.notna().sum() >= minimum:
            result[position] = sample.iloc[0 if first else -1]
    return pd.Series(result)


def _rolling_position(
    values: pd.Series,
    window: int,
    minimum: int,
    *,
    maximum: bool,
) -> pd.Series:
    """返回极值在当前物理窗口中的零基位置，NULL 不参与极值选择。"""
    result = np.full(len(values), np.nan)
    for position in range(len(values)):
        start = max(0, position - window + 1)
        sample = values.iloc[start : position + 1].to_numpy(dtype=float)
        if np.isfinite(sample).sum() < minimum:
            continue
        result[position] = (
            np.nanargmax(sample) if maximum else np.nanargmin(sample)
        )
    return pd.Series(result)


def _rolling_mad(values: pd.Series, window: int, minimum: int) -> pd.Series:
    """计算跳过 NULL 的窗口中位绝对离差。"""
    def median_deviation(sample: np.ndarray) -> float:
        """只使用窗口内有限观测计算中位绝对离差。"""
        valid = sample[np.isfinite(sample)]
        return float(np.median(np.abs(valid - np.median(valid))))

    return values.rolling(window, min_periods=minimum).apply(
        median_deviation,
        raw=True,
    )


def _rolling_moment(
    values: pd.Series,
    window: int,
    minimum: int,
    order: int,
) -> pd.Series:
    """计算总体标准化三阶矩或 Pearson 四阶矩。"""
    def moment(sample: np.ndarray) -> float:
        """对当前有效窗口计算标准化中心矩。"""
        valid = sample[np.isfinite(sample)]
        centered = valid - valid.mean()
        variance = np.mean(centered**2)
        if variance == 0:
            return 0.0
        return float(np.mean(centered**order) / variance ** (order / 2))

    return values.rolling(window, min_periods=minimum).apply(moment, raw=True)


def _decay_linear(values: pd.Series, window: int, minimum: int) -> pd.Series:
    """使用固定物理窗口中的 1..window 权重计算线性衰减平均。"""
    result = np.full(len(values), np.nan)
    weights = np.arange(1.0, window + 1.0)
    for position in range(window - 1, len(values)):
        sample = values.iloc[position - window + 1 : position + 1].to_numpy(float)
        valid = np.isfinite(sample)
        if valid.sum() >= minimum:
            result[position] = np.average(sample[valid], weights=weights[valid])
    return pd.Series(result)


def _rolling_booleans(
    values: pd.Series,
    window: int,
    minimum: int,
    mode: str,
) -> pd.Series:
    """复现滚动 BOOL 算符的行数门槛和有效值门槛。"""
    result: list[object] = []
    for position in range(len(values)):
        start = max(0, position - window + 1)
        sample = values.iloc[start : position + 1]
        valid = sample.dropna().astype(bool)
        row_count = len(sample)
        true_count = int(valid.sum())
        if mode == "count":
            result.append(np.nan if row_count < minimum else true_count)
        elif mode == "any":
            result.append(row_count >= minimum and true_count > 0)
        elif mode == "all":
            result.append(
                len(valid) >= minimum and true_count == len(valid)
            )
        else:
            raise AssertionError(f"未知 BOOL 滚动方法 {mode}")
    return pd.Series(result)


def _bars_since(values: pd.Series) -> pd.Series:
    """计算距最近 true 的观测行数。"""
    result = np.full(len(values), np.nan)
    last: int | None = None
    for position, value in enumerate(values):
        if value is True:
            last = position
        if last is not None:
            result[position] = position - last
    return pd.Series(result)


def _consecutive_true(values: pd.Series) -> pd.Series:
    """true 累加、false 清零、NULL 保持当前连续计数。"""
    result: list[int] = []
    count = 0
    for value in values:
        if value is True:
            count += 1
        elif value is False:
            count = 0
        result.append(count)
    return pd.Series(result)


def _changed(values: pd.Series, *, null_equal: bool) -> pd.Series:
    """按相邻物理观测及可配置的连续 NULL 语义判断变化。"""
    result = [True]
    for previous, current in zip(values.iloc[:-1], values.iloc[1:], strict=True):
        previous_null = pd.isna(previous)
        current_null = pd.isna(current)
        if previous_null and current_null:
            result.append(not null_equal)
        elif previous_null or current_null:
            result.append(True)
        else:
            result.append(bool(previous != current))
    return pd.Series(result)


def _crossing(left: pd.Series, right: pd.Series, *, above: bool) -> pd.Series:
    """交叉要求当前与前一期四个值均有效，首行固定为 false。"""
    result = [False]
    for position in range(1, len(left)):
        values = (
            left.iloc[position],
            right.iloc[position],
            left.iloc[position - 1],
            right.iloc[position - 1],
        )
        if any(pd.isna(value) for value in values):
            result.append(False)
            continue
        if above:
            result.append(values[0] > values[1] and values[2] <= values[3])
        else:
            result.append(values[0] < values[1] and values[2] >= values[3])
    return pd.Series(result)


def _rolling_regression(
    left: pd.Series,
    right: pd.Series,
    window: int,
    minimum: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """逐窗口使用成对有效值计算带截距 OLS 的斜率、截距和当前残差。"""
    slope = np.full(len(left), np.nan)
    intercept = np.full(len(left), np.nan)
    residual = np.full(len(left), np.nan)
    for position in range(len(left)):
        start = max(0, position - window + 1)
        x = left.iloc[start : position + 1].to_numpy(float)
        y = right.iloc[start : position + 1].to_numpy(float)
        valid = np.isfinite(x) & np.isfinite(y)
        if valid.sum() < minimum or np.var(x[valid]) == 0:
            continue
        design = np.column_stack([np.ones(valid.sum()), x[valid]])
        intercept[position], slope[position] = np.linalg.lstsq(
            design,
            y[valid],
            rcond=None,
        )[0]
        if pd.notna(left.iloc[position]) and pd.notna(right.iloc[position]):
            residual[position] = (
                right.iloc[position]
                - intercept[position]
                - slope[position] * left.iloc[position]
            )
    return pd.Series(slope), pd.Series(intercept), pd.Series(residual)


@pytest.fixture(scope="module")
def time_series_source() -> pd.DataFrame:
    """构造含缺失、并列、零值和 BOOL NULL 的十六期单股票序列。"""
    return pd.DataFrame(
        {
            "time": pd.date_range("2024-01-01", periods=16, freq="D"),
            "code": ["A"] * 16,
            "x": [1.0, 2.0, np.nan, 4.0, 2.0, 5.0, 5.0, 3.0, np.nan, 8.0, 7.0, 9.0, 6.0, 10.0, 10.0, 12.0],
            "y": [2.0, 1.0, 3.0, np.nan, 4.0, 6.0, 5.0, 4.0, 7.0, 8.0, np.nan, 10.0, 9.0, 11.0, 13.0, 12.0],
            "flag": [False, True, True, None, True, False, True, True, True, None, False, True, True, False, True, True],
        }
    )


def _time_series_contracts(source: pd.DataFrame) -> dict[str, TimeSeriesContract]:
    """显式定义全部非 TA-Lib 时序算符的独立契约。"""
    x = source["x"]
    y = source["y"]
    flag = source["flag"]
    window = 5
    minimum = 3
    rolling = x.rolling(window, min_periods=minimum)
    expanding = x.expanding(min_periods=minimum)
    slope, intercept, residual = _rolling_regression(x, y, window, minimum)

    pair_count = (x.notna() & y.notna()).cumsum()
    expanding_cov = x.expanding(min_periods=1).cov(y)
    expanding_corr = x.expanding(min_periods=1).corr(y)
    expanding_beta = expanding_cov / x.where(y.notna()).expanding(min_periods=1).var()
    pair_mask = pair_count < minimum
    expanding_cov[pair_mask] = np.nan
    expanding_corr[pair_mask] = np.nan
    expanding_beta[pair_mask] = np.nan

    ewm_arguments = {
        "span": 4.0,
        "min_periods": 2,
        "adjust": False,
        "ignore_na": True,
    }
    pandas_ewm = x.ewm(**ewm_arguments)
    dsl_ewm = {
        "span": 4.0,
        "min_periods": 2,
        "adjust": False,
        "ignore_na": True,
    }

    contracts = {
        "binary.cross_above": TimeSeriesContract(_ts("binary.cross_above", {"left": "x", "right": "y"}), _crossing(x, y, above=True)),
        "binary.cross_below": TimeSeriesContract(_ts("binary.cross_below", {"left": "x", "right": "y"}), _crossing(x, y, above=False)),
        "binary.ewm_corr": TimeSeriesContract(_ts("binary.ewm_corr", {"left": "x", "right": "y"}, {**dsl_ewm, "bias": False}), pandas_ewm.corr(y)),
        "binary.ewm_cov": TimeSeriesContract(_ts("binary.ewm_cov", {"left": "x", "right": "y"}, {**dsl_ewm, "bias": False}), pandas_ewm.cov(y, bias=False)),
        "binary.expanding_beta": TimeSeriesContract(_ts("binary.expanding_beta", {"left": "x", "right": "y"}, {"min_periods": minimum}), expanding_beta),
        "binary.expanding_corr": TimeSeriesContract(_ts("binary.expanding_corr", {"left": "x", "right": "y"}, {"min_periods": minimum}), expanding_corr),
        "binary.expanding_cov": TimeSeriesContract(_ts("binary.expanding_cov", {"left": "x", "right": "y"}, {"min_periods": minimum}), expanding_cov),
        "binary.rolling_alpha": TimeSeriesContract(_ts("binary.rolling_alpha", {"left": "x", "right": "y"}, {"window": window, "min_periods": minimum}), intercept),
        "binary.rolling_beta": TimeSeriesContract(_ts("binary.rolling_beta", {"left": "x", "right": "y"}, {"window": window, "min_periods": minimum}), slope),
        "binary.rolling_corr": TimeSeriesContract(_ts("binary.rolling_corr", {"left": "x", "right": "y"}, {"window": window, "min_periods": minimum}), x.rolling(window, min_periods=minimum).corr(y)),
        "binary.rolling_cov": TimeSeriesContract(_ts("binary.rolling_cov", {"left": "x", "right": "y"}, {"window": window, "min_periods": minimum}), x.rolling(window, min_periods=minimum).cov(y)),
        "binary.rolling_residual": TimeSeriesContract(_ts("binary.rolling_residual", {"left": "x", "right": "y"}, {"window": window, "min_periods": minimum}), residual),
        "unary.bars_since": TimeSeriesContract(_ts("unary.bars_since", {"col": "flag"}), _bars_since(flag)),
        "unary.bfill": TimeSeriesContract(_ts("unary.bfill", {"col": "x"}, {"limit": 2}), x.bfill(limit=2)),
        "unary.changed": TimeSeriesContract(_ts("unary.changed", {"col": "x"}, {"null_equal": False}), _changed(x, null_equal=False)),
        "unary.consecutive_count": TimeSeriesContract(_ts("unary.consecutive_count", {"col": "flag"}), _consecutive_true(flag)),
        "unary.cum_count": TimeSeriesContract(_ts("unary.cum_count", {"col": "x"}, {"min_periods": minimum}), _expanding_aggregate(x, minimum, "count")),
        "unary.cum_max": TimeSeriesContract(_ts("unary.cum_max", {"col": "x"}, {"min_periods": minimum}), _expanding_aggregate(x, minimum, "max")),
        "unary.cum_mean": TimeSeriesContract(_ts("unary.cum_mean", {"col": "x"}, {"min_periods": minimum}), _expanding_aggregate(x, minimum, "mean")),
        "unary.cum_min": TimeSeriesContract(_ts("unary.cum_min", {"col": "x"}, {"min_periods": minimum}), _expanding_aggregate(x, minimum, "min")),
        "unary.cum_prod": TimeSeriesContract(_ts("unary.cum_prod", {"col": "x"}, {"min_periods": minimum}), _expanding_aggregate(x, minimum, "prod")),
        "unary.cum_sum": TimeSeriesContract(_ts("unary.cum_sum", {"col": "x"}, {"min_periods": minimum}), _expanding_aggregate(x, minimum, "sum")),
        "unary.decay_linear": TimeSeriesContract(_ts("unary.decay_linear", {"col": "x"}, {"window": window, "min_periods": minimum}), _decay_linear(x, window, minimum)),
        "unary.diff": TimeSeriesContract(_ts("unary.diff", {"col": "x"}, {"periods": 2}), x.diff(2)),
        "unary.ewm_mean": TimeSeriesContract(_ts("unary.ewm_mean", {"col": "x"}, dsl_ewm), pandas_ewm.mean()),
        "unary.ewm_std": TimeSeriesContract(_ts("unary.ewm_std", {"col": "x"}, {**dsl_ewm, "bias": False}), pandas_ewm.std(bias=False)),
        "unary.ewm_var": TimeSeriesContract(_ts("unary.ewm_var", {"col": "x"}, {**dsl_ewm, "bias": False}), pandas_ewm.var(bias=False)),
        "unary.expanding_median": TimeSeriesContract(_ts("unary.expanding_median", {"col": "x"}, {"min_periods": minimum}), expanding.median()),
        "unary.expanding_quantile": TimeSeriesContract(_ts("unary.expanding_quantile", {"col": "x"}, {"min_periods": minimum, "q": 0.35}), expanding.quantile(0.35)),
        "unary.expanding_rank": TimeSeriesContract(_ts("unary.expanding_rank", {"col": "x"}, {"min_periods": minimum, "ascending": True, "ties_method": "min"}), _current_rank(x, window=None, minimum=minimum, ascending=True, method="min", percent=False)),
        "unary.expanding_rank_pct": TimeSeriesContract(_ts("unary.expanding_rank_pct", {"col": "x"}, {"min_periods": minimum, "ascending": True, "ties_method": "min"}), _current_rank(x, window=None, minimum=minimum, ascending=True, method="min", percent=True)),
        "unary.expanding_sem": TimeSeriesContract(_ts("unary.expanding_sem", {"col": "x"}, {"min_periods": minimum}), expanding.std() / np.sqrt(expanding.count())),
        "unary.expanding_std": TimeSeriesContract(_ts("unary.expanding_std", {"col": "x"}, {"min_periods": minimum}), expanding.std()),
        "unary.expanding_var": TimeSeriesContract(_ts("unary.expanding_var", {"col": "x"}, {"min_periods": minimum}), expanding.var()),
        "unary.ffill": TimeSeriesContract(_ts("unary.ffill", {"col": "x"}, {"limit": 2}), x.ffill(limit=2)),
        "unary.log_return": TimeSeriesContract(_ts("unary.log_return", {"col": "x"}, {"periods": 2}), np.log(x) - np.log(x).shift(2)),
        "unary.pct_change": TimeSeriesContract(_ts("unary.pct_change", {"col": "x"}, {"periods": 2}), x.pct_change(2, fill_method=None)),
        "unary.rolling_all": TimeSeriesContract(_ts("unary.rolling_all", {"col": "flag"}, {"window": window, "min_periods": minimum}), _rolling_booleans(flag, window, minimum, "all")),
        "unary.rolling_any": TimeSeriesContract(_ts("unary.rolling_any", {"col": "flag"}, {"window": window, "min_periods": minimum}), _rolling_booleans(flag, window, minimum, "any")),
        "unary.rolling_argmax": TimeSeriesContract(_ts("unary.rolling_argmax", {"col": "x"}, {"window": window, "min_periods": minimum}), _rolling_position(x, window, minimum, maximum=True)),
        "unary.rolling_argmin": TimeSeriesContract(_ts("unary.rolling_argmin", {"col": "x"}, {"window": window, "min_periods": minimum}), _rolling_position(x, window, minimum, maximum=False)),
        "unary.rolling_count": TimeSeriesContract(_ts("unary.rolling_count", {"col": "x"}, {"window": window, "min_periods": minimum}), rolling.count().where(rolling.count() >= minimum)),
        "unary.rolling_first": TimeSeriesContract(_ts("unary.rolling_first", {"col": "x"}, {"window": window, "min_periods": minimum}), _rolling_endpoint(x, window, minimum, first=True)),
        "unary.rolling_kurt": TimeSeriesContract(_ts("unary.rolling_kurt", {"col": "x"}, {"window": window, "min_periods": minimum}), _rolling_moment(x, window, minimum, 4)),
        "unary.rolling_last": TimeSeriesContract(_ts("unary.rolling_last", {"col": "x"}, {"window": window, "min_periods": minimum}), _rolling_endpoint(x, window, minimum, first=False)),
        "unary.rolling_mad": TimeSeriesContract(_ts("unary.rolling_mad", {"col": "x"}, {"window": window, "min_periods": minimum}), _rolling_mad(x, window, minimum)),
        "unary.rolling_max": TimeSeriesContract(_ts("unary.rolling_max", {"col": "x"}, {"window": window, "min_periods": minimum}), rolling.max()),
        "unary.rolling_mean": TimeSeriesContract(_ts("unary.rolling_mean", {"col": "x"}, {"window": window, "min_periods": minimum}), rolling.mean()),
        "unary.rolling_median": TimeSeriesContract(_ts("unary.rolling_median", {"col": "x"}, {"window": window, "min_periods": minimum}), rolling.median()),
        "unary.rolling_min": TimeSeriesContract(_ts("unary.rolling_min", {"col": "x"}, {"window": window, "min_periods": minimum}), rolling.min()),
        "unary.rolling_prod": TimeSeriesContract(_ts("unary.rolling_prod", {"col": "x"}, {"window": window, "min_periods": minimum}), rolling.apply(np.nanprod, raw=True)),
        "unary.rolling_quantile": TimeSeriesContract(_ts("unary.rolling_quantile", {"col": "x"}, {"window": window, "min_periods": minimum, "q": 0.35}), rolling.quantile(0.35, interpolation="linear")),
        "unary.rolling_rank": TimeSeriesContract(_ts("unary.rolling_rank", {"col": "x"}, {"window": window, "min_periods": minimum, "ascending": True, "ties_method": "min"}), _current_rank(x, window=window, minimum=minimum, ascending=True, method="min", percent=False)),
        "unary.rolling_rank_pct": TimeSeriesContract(_ts("unary.rolling_rank_pct", {"col": "x"}, {"window": window, "min_periods": minimum, "ascending": True, "ties_method": "min"}), _current_rank(x, window=window, minimum=minimum, ascending=True, method="min", percent=True)),
        "unary.rolling_sem": TimeSeriesContract(_ts("unary.rolling_sem", {"col": "x"}, {"window": window, "min_periods": minimum}), rolling.std() / np.sqrt(rolling.count())),
        "unary.rolling_skew": TimeSeriesContract(_ts("unary.rolling_skew", {"col": "x"}, {"window": window, "min_periods": minimum}), _rolling_moment(x, window, minimum, 3)),
        "unary.rolling_std": TimeSeriesContract(_ts("unary.rolling_std", {"col": "x"}, {"window": window, "min_periods": minimum}), rolling.std()),
        "unary.rolling_sum": TimeSeriesContract(_ts("unary.rolling_sum", {"col": "x"}, {"window": window, "min_periods": minimum}), rolling.sum()),
        "unary.rolling_true_count": TimeSeriesContract(_ts("unary.rolling_true_count", {"col": "flag"}, {"window": window, "min_periods": minimum}), _rolling_booleans(flag, window, minimum, "count")),
        "unary.rolling_var": TimeSeriesContract(_ts("unary.rolling_var", {"col": "x"}, {"window": window, "min_periods": minimum}), rolling.var()),
        "unary.rolling_zscore": TimeSeriesContract(_ts("unary.rolling_zscore", {"col": "x"}, {"window": window, "min_periods": minimum}), (x - rolling.mean()) / rolling.std()),
        "unary.shift": TimeSeriesContract(_ts("unary.shift", {"col": "x"}, {"periods": 2}), x.shift(2)),
    }
    return contracts


def _registered_non_talib() -> set[str]:
    """返回注册的非 TA-Lib TS 算符名称。"""
    return {
        operation
        for operation, model in Derivative.operators.items()
        if issubclass(model, TimeSeriesOperator) and not operation.startswith("talib.")
    }


def test_time_series_contract_inventory_is_exhaustive(
    time_series_source: pd.DataFrame,
) -> None:
    """显式时序 oracle 清单必须覆盖全部 62 个非 TA-Lib 算符。"""
    registered = _registered_non_talib()
    assert set(_time_series_contracts(time_series_source)) == registered
    assert len(registered) == 62


@pytest.mark.parametrize("operation", sorted(_registered_non_talib()))
def test_time_series_operator_matches_independent_reference(
    ddb_session,
    time_series_source: pd.DataFrame,
    operation: str,
) -> None:
    """每个非 TA-Lib TS 算符经完整 JSON DSL 与十六期参考结果比较。"""
    contract = _time_series_contracts(time_series_source)[operation]
    result = compute_factors(
        ddb_session,
        time_series_source,
        {"actual": contract.definition},
    )
    assert_vector_equal(result["actual"], contract.expected, atol=1e-7, rtol=1e-7)


@pytest.mark.parametrize("operation", ["unary.ewm_mean", "unary.ewm_std", "unary.ewm_var", "binary.ewm_cov", "binary.ewm_corr"])
@pytest.mark.parametrize(
    ("decay_name", "decay_value"),
    [("com", 2.5), ("span", 6.0), ("half_life", 3.0), ("alpha", 0.35)],
)
def test_ewm_all_decay_dispatch_branches(
    ddb_session,
    time_series_source: pd.DataFrame,
    operation: str,
    decay_name: str,
    decay_value: float,
) -> None:
    """五个 EWM 算符的四种互斥衰减参数都必须与 Pandas 一致。"""
    binary = operation.startswith("binary.")
    params: dict[str, Any] = {
        decay_name: decay_value,
        "min_periods": 2,
        "adjust": True,
        "ignore_na": False,
    }
    if operation != "unary.ewm_mean":
        params["bias"] = True
    fields = {"left": "x", "right": "y"} if binary else {"col": "x"}
    definition = _ts(operation, fields, params)

    pandas_params = {
        decay_name if decay_name != "half_life" else "halflife": decay_value,
        "min_periods": 2,
        "adjust": True,
        "ignore_na": False,
    }
    ewm = time_series_source["x"].ewm(**pandas_params)
    if operation == "unary.ewm_mean":
        expected = ewm.mean()
    elif operation == "unary.ewm_std":
        expected = ewm.std(bias=True)
    elif operation == "unary.ewm_var":
        expected = ewm.var(bias=True)
    elif operation == "binary.ewm_cov":
        expected = ewm.cov(time_series_source["y"], bias=True)
    else:
        expected = ewm.corr(time_series_source["y"])

    result = compute_factors(ddb_session, time_series_source, {"actual": definition})
    assert_vector_equal(result["actual"], expected, atol=1e-7, rtol=1e-7)


@pytest.mark.parametrize(
    ("operation", "ties_method"),
    [
        *((operation, method) for operation in ["unary.expanding_rank", "unary.expanding_rank_pct"] for method in ["min", "max", "average", "dense"]),
        *((operation, method) for operation in ["unary.rolling_rank", "unary.rolling_rank_pct"] for method in ["min", "max", "average"]),
    ],
)
@pytest.mark.parametrize("ascending", [True, False])
def test_time_series_rank_all_directions_and_tie_methods(
    ddb_session,
    time_series_source: pd.DataFrame,
    operation: str,
    ascending: bool,
    ties_method: str,
) -> None:
    """扩展与滚动排名覆盖方向、并列规则、百分比和 NULL 当前值。"""
    rolling = "rolling" in operation
    percent = operation.endswith("_pct")
    params: dict[str, object] = {
        "min_periods": 2,
        "ascending": ascending,
        "ties_method": ties_method,
    }
    if rolling:
        params["window"] = 6
    expected = _current_rank(
        time_series_source["x"],
        window=6 if rolling else None,
        minimum=2,
        ascending=ascending,
        method=ties_method,
        percent=percent,
    )
    result = compute_factors(
        ddb_session,
        time_series_source,
        {"actual": _ts(operation, {"col": "x"}, params)},
    )
    assert_vector_equal(result["actual"], expected, atol=1e-8, rtol=1e-8)


@pytest.mark.parametrize("operation", ["unary.ffill", "unary.bfill"])
@pytest.mark.parametrize("limit", [None, 1, 3])
def test_fill_unlimited_and_segment_limits(
    ddb_session,
    operation: str,
    limit: int | None,
) -> None:
    """前后填充分辨无限制及每段连续 NULL 的限制。"""
    values = pd.Series([np.nan, 1.0, np.nan, np.nan, np.nan, 5.0, np.nan, 7.0, np.nan, np.nan, np.nan, np.nan])
    source = pd.DataFrame(
        {
            "time": pd.date_range("2024-01-01", periods=len(values)),
            "code": ["A"] * len(values),
            "value": values,
        }
    )
    expected = values.ffill(limit=limit) if operation.endswith("ffill") else values.bfill(limit=limit)
    result = compute_factors(
        ddb_session,
        source,
        {"actual": _ts(operation, {"col": "value"}, {"limit": limit})},
    )
    assert_vector_equal(result["actual"], expected)


@pytest.mark.parametrize("null_equal", [True, False])
def test_changed_consecutive_null_policy(ddb_session, null_equal: bool) -> None:
    """changed 明确区分连续 NULL 算相同或算变化的两种策略。"""
    values = pd.Series([1.0, 1.0, np.nan, np.nan, 2.0, 2.0, np.nan, 3.0, 3.0, np.nan])
    source = pd.DataFrame(
        {
            "time": pd.date_range("2024-01-01", periods=len(values)),
            "code": ["A"] * len(values),
            "value": values,
        }
    )
    result = compute_factors(
        ddb_session,
        source,
        {"actual": _ts("unary.changed", {"col": "value"}, {"null_equal": null_equal})},
    )
    assert_vector_equal(result["actual"], _changed(values, null_equal=null_equal))
