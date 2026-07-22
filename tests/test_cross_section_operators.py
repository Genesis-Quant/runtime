"""使用 NumPy/Pandas 独立结果验证全部截面算符。"""

from dataclasses import dataclass
from statistics import NormalDist
from typing import Any, Callable

import numpy as np
import pandas as pd
import pytest

from core.operators import Derivative
from core.operators.base import CrossSectionOperator
from tests.support.assertions import assert_vector_equal
from tests.support.dsl import TRUE_NODE, compute_factors, cross_section
from tests.support.panel import apply_cross_section, neutralize, zscore


@dataclass(frozen=True)
class CrossSectionContract:
    """保存单个截面算符的完整 DSL 与独立期望结果。"""

    definition: dict[str, object]
    expected: object


def _cs(
    operation: str,
    fields: dict[str, object],
    params: dict[str, object] | None = None,
) -> dict[str, object]:
    """构造对全部输入行启用的 CS 节点。"""
    return cross_section(operation, fields, params, on=TRUE_NODE)


def _by_date(
    source: pd.DataFrame,
    calculator: Callable[[pd.DataFrame], Any],
    *,
    by: str | None = None,
    dtype: str | type = "float64",
) -> pd.Series:
    """逐日期或逐日期分类组计算并按原索引回填。"""
    return apply_cross_section(
        source,
        pd.Series(True, index=source.index),
        calculator,
        by=by,
        dtype=dtype,
    )


def _broadcast(value: object, size: int) -> list[object]:
    """把单个截面统计量广播到当前组全部行。"""
    return [value] * size


def _population_moment(values: pd.Series, order: int) -> float:
    """计算跳过 NULL 的总体标准化中心矩。"""
    valid = values.dropna().to_numpy(float)
    if len(valid) == 0:
        return np.nan
    centered = valid - valid.mean()
    variance = np.mean(centered**2)
    if variance == 0:
        return 0.0
    return float(np.mean(centered**order) / variance ** (order / 2))


def _qcut(values: pd.Series, q: int) -> pd.Series:
    """按最小并列名次和有效样本数生成零基等频箱。"""
    valid_count = values.notna().sum()
    rank = values.rank(method="min", ascending=True) - 1
    return np.floor(rank * q / valid_count)


def _rank_normal(values: pd.Series, ascending: bool) -> pd.Series:
    """使用平均并列名次和标准正态逆分布转换截面排名。"""
    count = values.notna().sum()
    ranks = values.rank(method="average", ascending=ascending)
    probabilities = (ranks - 0.5) / count
    normal = NormalDist()
    return probabilities.map(
        lambda value: np.nan if pd.isna(value) else normal.inv_cdf(float(value))
    )


def _select_extreme(
    values: pd.Series,
    count: int,
    *,
    ascending: bool,
) -> pd.Series:
    """按原行顺序打破并列，选择指定数量的有效极值。"""
    ranks = values.rank(method="first", ascending=ascending)
    return values.notna() & (ranks <= count)


def _regression_values(group: pd.DataFrame) -> dict[str, object]:
    """计算 right 关于 left 的成对 OLS、相关和边际秩相关。"""
    left = group["reg_x"]
    right = group["reg_y"]
    valid = left.notna() & right.notna()
    x = left.loc[valid].to_numpy(float)
    y = right.loc[valid].to_numpy(float)
    if len(x) < 2 or np.var(x) == 0:
        slope = intercept = np.nan
    else:
        design = np.column_stack([np.ones(len(x)), x])
        intercept, slope = np.linalg.lstsq(design, y, rcond=None)[0]
    residual = pd.Series(np.nan, index=group.index)
    if np.isfinite(slope):
        residual.loc[valid] = y - intercept - slope * x
    paired_left = pd.Series(x)
    paired_right = pd.Series(y)
    return {
        "alpha": intercept,
        "beta": slope,
        "corr": left.corr(right),
        "cov": left.cov(right),
        "rank_corr": paired_left.rank(method="average").corr(
            paired_right.rank(method="average")
        ),
        "residual": residual,
    }


@pytest.fixture(scope="module")
def cross_section_source() -> pd.DataFrame:
    """构造两日、含并列/缺失/分类及连续控制变量的真实截面形状。"""
    first_x = [1.0, 2.0, 2.0, 4.0, 8.0, np.nan, -3.0, 5.0, 5.0, 10.0, 0.0, 6.0]
    second_x = [3.0, 3.0, 6.0, 9.0, np.nan, 12.0, -6.0, 0.0, 15.0, 3.0, 18.0, 21.0]
    industry = ["bank", "bank", "tech", "tech", "retail", "retail", None, "bank", "tech", "retail", "bank", "tech"]
    size = [10.0, 12.0, 8.0, 11.0, 9.0, 13.0, 7.0, 14.0, np.nan, 15.0, 6.0, 16.0]
    flag = [True, False, True, False, True, False, True, False, True, False, True, False]

    frame = pd.DataFrame(
        {
            "time": pd.to_datetime(["2024-01-02"] * 12 + ["2024-01-03"] * 12),
            "code": [f"S{index:02d}" for index in range(12)] * 2,
            "x": first_x + second_x,
            "reg_x": [1.0, np.nan, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0]
            + [2.0, 4.0, 6.0, 8.0, np.nan, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0],
            "reg_y": [2.0, 4.0, 6.0, np.nan, 9.0, 13.0, 14.0, 15.0, 19.0, 18.0, 23.0, 25.0]
            + [5.0, 7.0, np.nan, 17.0, 20.0, 25.0, 27.0, 34.0, 35.0, 42.0, 43.0, 49.0],
            "industry": industry * 2,
            "size": size + [value + 2 if pd.notna(value) else np.nan for value in size],
            "flag": flag * 2,
        }
    )
    effects = {"bank": -1.0, "tech": 0.5, "retail": 2.0}
    noise = np.array([0.2, -0.1, 0.3, -0.4, 0.5, -0.2, 0.1, -0.3, 0.4, -0.5, 0.6, -0.6] * 2)
    frame["target"] = (
        1.5
        + 0.4 * frame["size"]
        + frame["industry"].map(effects)
        + frame["flag"].astype(float) * 0.8
        + noise
    )
    frame.loc[3, "target"] = np.nan
    frame.loc[17, "target"] = np.nan
    return frame


def _cross_section_contracts(
    source: pd.DataFrame,
) -> dict[str, CrossSectionContract]:
    """显式定义全部 40 个截面算符的独立计算契约。"""
    rank = lambda group, method, pct=False, ascending=True: group["x"].rank(
        method=method,
        ascending=ascending,
        pct=pct,
        na_option="keep",
    )

    def binary_scalar(name: str) -> pd.Series:
        """按日广播一个独立二元截面统计量。"""
        return _by_date(
            source,
            lambda group: _broadcast(_regression_values(group)[name], len(group)),
        )

    def unary_scalar(calculator: Callable[[pd.Series], object]) -> pd.Series:
        """按日广播一个独立一元截面统计量。"""
        return _by_date(
            source,
            lambda group: _broadcast(calculator(group["x"]), len(group)),
        )

    controls_expected = _by_date(
        source,
        lambda group: neutralize(
            group["target"],
            group[["industry", "size", "flag"]],
            intercept=True,
        ),
    )

    contracts = {
        "binary.alpha": CrossSectionContract(_cs("binary.alpha", {"left": "reg_x", "right": "reg_y"}), binary_scalar("alpha")),
        "binary.beta": CrossSectionContract(_cs("binary.beta", {"left": "reg_x", "right": "reg_y"}), binary_scalar("beta")),
        "binary.corr": CrossSectionContract(_cs("binary.corr", {"left": "reg_x", "right": "reg_y"}), binary_scalar("corr")),
        "binary.cov": CrossSectionContract(_cs("binary.cov", {"left": "reg_x", "right": "reg_y"}), binary_scalar("cov")),
        "binary.rank_corr": CrossSectionContract(_cs("binary.rank_corr", {"left": "reg_x", "right": "reg_y"}), binary_scalar("rank_corr")),
        "binary.residual": CrossSectionContract(_cs("binary.residual", {"left": "reg_x", "right": "reg_y"}), _by_date(source, lambda group: _regression_values(group)["residual"])),
        "controls.neutralize_by": CrossSectionContract(_cs("controls.neutralize_by", {"target": "target", "controls": ["industry", "size", "flag"]}, {"intercept": True}), controls_expected),
        "grouped.demean": CrossSectionContract(_cs("grouped.demean", {"col": "x", "by": "industry"}), _by_date(source, lambda group: group["x"] - group["x"].mean(), by="industry")),
        "grouped.mean": CrossSectionContract(_cs("grouped.mean", {"col": "x", "by": "industry"}), _by_date(source, lambda group: _broadcast(group["x"].mean(), len(group)), by="industry")),
        "grouped.rank_pct": CrossSectionContract(_cs("grouped.rank_pct", {"col": "x", "by": "industry"}, {"ascending": True, "ties_method": "min"}), _by_date(source, lambda group: group["x"].rank(method="min", pct=True), by="industry")),
        "grouped.zscore": CrossSectionContract(_cs("grouped.zscore", {"col": "x", "by": "industry"}, {"ddof": 1}), _by_date(source, lambda group: zscore(group["x"], 1), by="industry")),
        "unary.bottom_n": CrossSectionContract(_cs("unary.bottom_n", {"col": "x"}, {"n": 3}), _by_date(source, lambda group: _select_extreme(group["x"], 3, ascending=True), dtype=object)),
        "unary.bottom_pct": CrossSectionContract(_cs("unary.bottom_pct", {"col": "x"}, {"pct": 0.25}), _by_date(source, lambda group: _select_extreme(group["x"], int(np.ceil(group["x"].notna().sum() * 0.25)), ascending=True), dtype=object)),
        "unary.count": CrossSectionContract(_cs("unary.count", {"col": "x"}), unary_scalar(lambda values: values.count())),
        "unary.demean": CrossSectionContract(_cs("unary.demean", {"col": "x"}), _by_date(source, lambda group: group["x"] - group["x"].mean())),
        "unary.kurt": CrossSectionContract(_cs("unary.kurt", {"col": "x"}), unary_scalar(lambda values: _population_moment(values, 4))),
        "unary.mad": CrossSectionContract(_cs("unary.mad", {"col": "x"}), unary_scalar(lambda values: np.median(np.abs(values.dropna() - values.dropna().median())))),
        "unary.max": CrossSectionContract(_cs("unary.max", {"col": "x"}), unary_scalar(lambda values: values.max())),
        "unary.mean": CrossSectionContract(_cs("unary.mean", {"col": "x"}), unary_scalar(lambda values: values.mean())),
        "unary.median": CrossSectionContract(_cs("unary.median", {"col": "x"}), unary_scalar(lambda values: values.median())),
        "unary.min": CrossSectionContract(_cs("unary.min", {"col": "x"}), unary_scalar(lambda values: values.min())),
        "unary.normalize_l1": CrossSectionContract(_cs("unary.normalize_l1", {"col": "x"}), _by_date(source, lambda group: group["x"] / group["x"].abs().sum())),
        "unary.normalize_l2": CrossSectionContract(_cs("unary.normalize_l2", {"col": "x"}), _by_date(source, lambda group: group["x"] / np.sqrt((group["x"] ** 2).sum()))),
        "unary.normalize_sum": CrossSectionContract(_cs("unary.normalize_sum", {"col": "x"}), _by_date(source, lambda group: group["x"] / group["x"].sum())),
        "unary.qcut": CrossSectionContract(_cs("unary.qcut", {"col": "x"}, {"q": 4}), _by_date(source, lambda group: _qcut(group["x"], 4))),
        "unary.quantile": CrossSectionContract(_cs("unary.quantile", {"col": "x"}, {"q": 0.35}), unary_scalar(lambda values: values.quantile(0.35, interpolation="linear"))),
        "unary.rank": CrossSectionContract(_cs("unary.rank", {"col": "x"}, {"ascending": True, "ties_method": "min"}), _by_date(source, lambda group: rank(group, "min"))),
        "unary.rank_dense": CrossSectionContract(_cs("unary.rank_dense", {"col": "x"}, {"ascending": True}), _by_date(source, lambda group: rank(group, "dense"))),
        "unary.rank_normal": CrossSectionContract(_cs("unary.rank_normal", {"col": "x"}, {"ascending": True}), _by_date(source, lambda group: _rank_normal(group["x"], True))),
        "unary.rank_pct": CrossSectionContract(_cs("unary.rank_pct", {"col": "x"}, {"ascending": True, "ties_method": "min"}), _by_date(source, lambda group: rank(group, "min", pct=True))),
        "unary.robust_zscore": CrossSectionContract(_cs("unary.robust_zscore", {"col": "x"}, {"scale": 1.4826}), _by_date(source, lambda group: (group["x"] - group["x"].median()) / (np.median(np.abs(group["x"].dropna() - group["x"].median())) * 1.4826))),
        "unary.skew": CrossSectionContract(_cs("unary.skew", {"col": "x"}), unary_scalar(lambda values: _population_moment(values, 3))),
        "unary.std": CrossSectionContract(_cs("unary.std", {"col": "x"}, {"ddof": 1}), unary_scalar(lambda values: values.std(ddof=1))),
        "unary.sum": CrossSectionContract(_cs("unary.sum", {"col": "x"}), unary_scalar(lambda values: values.sum(min_count=1))),
        "unary.top_n": CrossSectionContract(_cs("unary.top_n", {"col": "x"}, {"n": 3}), _by_date(source, lambda group: _select_extreme(group["x"], 3, ascending=False), dtype=object)),
        "unary.top_pct": CrossSectionContract(_cs("unary.top_pct", {"col": "x"}, {"pct": 0.25}), _by_date(source, lambda group: _select_extreme(group["x"], int(np.ceil(group["x"].notna().sum() * 0.25)), ascending=False), dtype=object)),
        "unary.var": CrossSectionContract(_cs("unary.var", {"col": "x"}, {"ddof": 1}), unary_scalar(lambda values: values.var(ddof=1))),
        "unary.winsorize": CrossSectionContract(_cs("unary.winsorize", {"col": "x"}, {"lower": 0.1, "upper": 0.9}), _by_date(source, lambda group: group["x"].clip(group["x"].quantile(0.1), group["x"].quantile(0.9)))),
        "unary.winsorize_mad": CrossSectionContract(_cs("unary.winsorize_mad", {"col": "x"}, {"n": 2.5, "scale": 1.4826}), _by_date(source, lambda group: group["x"].clip(group["x"].median() - 2.5 * 1.4826 * np.median(np.abs(group["x"].dropna() - group["x"].median())), group["x"].median() + 2.5 * 1.4826 * np.median(np.abs(group["x"].dropna() - group["x"].median()))))),
        "unary.zscore": CrossSectionContract(_cs("unary.zscore", {"col": "x"}, {"ddof": 1}), _by_date(source, lambda group: zscore(group["x"], 1))),
    }
    return contracts


def _registered_cross_section() -> set[str]:
    """返回全部已注册 CS 算符名称。"""
    return {
        operation
        for operation, model in Derivative.operators.items()
        if issubclass(model, CrossSectionOperator)
    }


def test_cross_section_contract_inventory_is_exhaustive(
    cross_section_source: pd.DataFrame,
) -> None:
    """显式 oracle 清单必须与全部 40 个 CS 算符完全一致。"""
    registered = _registered_cross_section()
    assert set(_cross_section_contracts(cross_section_source)) == registered
    assert len(registered) == 40


@pytest.mark.parametrize("operation", sorted(_registered_cross_section()))
def test_cross_section_operator_matches_independent_reference(
    ddb_session,
    cross_section_source: pd.DataFrame,
    operation: str,
) -> None:
    """每个 CS 算符经完整 JSON DSL 与两日真实截面参考结果比较。"""
    contract = _cross_section_contracts(cross_section_source)[operation]
    result = compute_factors(
        ddb_session,
        cross_section_source,
        {"actual": contract.definition},
    )
    assert_vector_equal(result["actual"], contract.expected, atol=1e-7, rtol=1e-7)


@pytest.mark.parametrize("operation", ["unary.rank", "unary.rank_pct", "grouped.rank_pct"])
@pytest.mark.parametrize("ascending", [True, False])
@pytest.mark.parametrize("ties_method", ["min", "max", "average", "first"])
def test_cross_section_rank_all_supported_options(
    ddb_session,
    cross_section_source: pd.DataFrame,
    operation: str,
    ascending: bool,
    ties_method: str,
) -> None:
    """普通、百分比和分组排名覆盖方向及全部受支持并列规则。"""
    grouped = operation.startswith("grouped.")
    percent = operation.endswith("_pct")
    fields = {"col": "x", "by": "industry"} if grouped else {"col": "x"}
    expected = _by_date(
        cross_section_source,
        lambda group: group["x"].rank(
            method=ties_method,
            ascending=ascending,
            pct=percent,
        ),
        by="industry" if grouped else None,
    )
    result = compute_factors(
        ddb_session,
        cross_section_source,
        {
            "actual": _cs(
                operation,
                fields,
                {"ascending": ascending, "ties_method": ties_method},
            )
        },
    )
    assert_vector_equal(result["actual"], expected)


@pytest.mark.parametrize("operation", ["unary.std", "unary.var", "unary.zscore", "grouped.zscore"])
@pytest.mark.parametrize("ddof", [0, 1])
def test_cross_section_dispersion_both_ddof_branches(
    ddb_session,
    cross_section_source: pd.DataFrame,
    operation: str,
    ddof: int,
) -> None:
    """标准差、方差及普通/分组 z-score 区分总体和样本口径。"""
    grouped = operation.startswith("grouped.")
    fields = {"col": "x", "by": "industry"} if grouped else {"col": "x"}
    if operation.endswith("std"):
        calculator = lambda group: _broadcast(group["x"].std(ddof=ddof), len(group))
    elif operation.endswith("var"):
        calculator = lambda group: _broadcast(group["x"].var(ddof=ddof), len(group))
    else:
        calculator = lambda group: zscore(group["x"], ddof)
    expected = _by_date(
        cross_section_source,
        calculator,
        by="industry" if grouped else None,
    )
    result = compute_factors(
        ddb_session,
        cross_section_source,
        {"actual": _cs(operation, fields, {"ddof": ddof})},
    )
    assert_vector_equal(result["actual"], expected, atol=1e-8, rtol=1e-8)


@pytest.mark.parametrize("intercept", [True, False])
def test_neutralize_mixed_controls_and_intercept_modes(
    ddb_session,
    cross_section_source: pd.DataFrame,
    intercept: bool,
) -> None:
    """混合分类、BOOL 和连续控制变量在两种截距模式下与 NumPy OLS 一致。"""
    expected = _by_date(
        cross_section_source,
        lambda group: neutralize(
            group["target"],
            group[["industry", "size", "flag"]],
            intercept=intercept,
        ),
    )
    definition = _cs(
        "controls.neutralize_by",
        {"target": "target", "controls": ["industry", "size", "flag"]},
        {"intercept": intercept},
    )
    result = compute_factors(ddb_session, cross_section_source, {"actual": definition})
    assert_vector_equal(result["actual"], expected, atol=1e-8, rtol=1e-8)


@pytest.mark.parametrize(
    ("target", "continuous", "category"),
    [
        ([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], [1.0] * 10, ["A"] * 10),
        ([1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], list(range(10)), ["A", "B"] * 5),
        ([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], [1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], ["A", "B"] * 5),
        ([np.nan] * 10, list(range(10)), ["A", "B"] * 5),
        ([5.0] * 10, list(range(10)), ["A", "B"] * 5),
    ],
)
def test_neutralize_missing_constant_and_degenerate_cases(
    ddb_session,
    target: list[float],
    continuous: list[float],
    category: list[str],
) -> None:
    """中性化覆盖常量控制、目标/控制缺失、全无效和常量目标。"""
    source = pd.DataFrame(
        {
            "time": pd.to_datetime(["2024-01-02"] * 10),
            "code": [f"S{index}" for index in range(10)],
            "target": target,
            "continuous": continuous,
            "category": category,
        }
    )
    expected = neutralize(
        source["target"],
        source[["continuous", "category"]],
        intercept=True,
    )
    definition = _cs(
        "controls.neutralize_by",
        {"target": "target", "controls": ["continuous", "category"]},
        {"intercept": True},
    )
    result = compute_factors(ddb_session, source, {"actual": definition})
    assert_vector_equal(result["actual"], expected, atol=1e-8, rtol=1e-8)


def test_zero_scale_cross_sections_return_null_not_infinity(ddb_session) -> None:
    """零方差、零范数和零和截面不得产生无穷值。"""
    source = pd.DataFrame(
        {
            "time": pd.to_datetime(["2024-01-02"] * 5 + ["2024-01-03"] * 5),
            "code": [f"S{index}" for index in range(5)] * 2,
            "constant": [3.0] * 5 + [0.0] * 5,
            "zero_sum": [-2.0, -1.0, 0.0, 1.0, 2.0] * 2,
        }
    )
    definitions = {
        "zscore": _cs("unary.zscore", {"col": "constant"}, {"ddof": 1}),
        "l1": _cs("unary.normalize_l1", {"col": "constant"}),
        "l2": _cs("unary.normalize_l2", {"col": "constant"}),
        "sum_norm": _cs("unary.normalize_sum", {"col": "zero_sum"}),
    }
    result = compute_factors(ddb_session, source, definitions)
    assert result["zscore"].isna().all()
    assert result.loc[5:, "l1"].isna().all()
    assert result.loc[5:, "l2"].isna().all()
    assert result["sum_norm"].isna().all()
