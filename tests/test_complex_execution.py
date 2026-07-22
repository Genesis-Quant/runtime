"""验证全算符退化路径及跨类别嵌套 DSL 的端到端语义。"""

from typing import Any

import numpy as np
import pandas as pd
import pytest

from core.query.operator import Derivative
from core.query.operator.base import DirectOperator
from tests.support.assertions import assert_vector_equal
from tests.support.contracts import canonical_definition
from tests.support.dsl import compute_factors, cross_section, direct, time_series
from tests.support.panel import (
    apply_cross_section,
    apply_time_series,
    bool_mask,
    neutralize,
    zscore,
)


def _execution_source() -> pd.DataFrame:
    """构造足以满足全部 TS/CS 字段类型要求的基础输入表。"""
    close = np.array([10.0, 10.8, 11.2, 10.6, 12.0, 12.4, 13.1, 12.7, 13.8, 14.2, 13.9, 14.8])
    return pd.DataFrame(
        {
            "time": pd.date_range("2024-01-02", periods=12, freq="B"),
            "code": ["A"] * 6 + ["B"] * 6,
            "x": close,
            "y": close * 1.5 + np.sin(np.arange(12)),
            "flag": [True, False] * 6,
            "active": [False] * 12,
            "industry": ["bank", "tech", "energy"] * 4,
            "size": np.linspace(10.0, 21.0, 12),
            "open": close - 0.2,
            "high": close + 0.8,
            "low": close - 0.7,
            "close": close,
            "volume": np.linspace(100_000.0, 210_000.0, 12),
        }
    )


CONTEXTUAL_OPERATIONS = tuple(
    sorted(
        operation
        for operation, model in Derivative.operators.items()
        if not issubclass(model, DirectOperator)
    )
)

BOOLEAN_INPUT_OPERATIONS = {
    "unary.bars_since",
    "unary.consecutive_count",
    "unary.rolling_all",
    "unary.rolling_any",
    "unary.rolling_true_count",
}


def _execution_definition(operation: str) -> dict[str, Any]:
    """把规范模型节点绑定到满足算符运行时数据类型的测试列。"""
    definition = canonical_definition(operation)
    if operation in BOOLEAN_INPUT_OPERATIONS:
        definition["fields"]["col"] = "flag"
    return definition


@pytest.mark.parametrize("operation", CONTEXTUAL_OPERATIONS)
def test_every_contextual_operator_handles_all_false_on(
    ddb_session: Any,
    operation: str,
) -> None:
    """全部 TS/CS 算符在没有入选行时都返回等长全 NULL 结果。"""
    source = _execution_source()
    result = compute_factors(
        ddb_session,
        source,
        {"actual": _execution_definition(operation)},
    )
    assert len(CONTEXTUAL_OPERATIONS) == 156
    assert len(result) == len(source)
    assert result["actual"].isna().all()


@pytest.mark.parametrize("operation", CONTEXTUAL_OPERATIONS)
def test_every_contextual_operator_handles_empty_source(
    ddb_session: Any,
    operation: str,
) -> None:
    """全部 TS/CS 算符必须接受保留列类型的零行输入表。"""
    source = _execution_source().iloc[:0]
    result = compute_factors(
        ddb_session,
        source,
        {"actual": _execution_definition(operation)},
    )
    assert result.empty
    assert list(result.columns) == [*source.columns, "actual"]


def _pipeline_source() -> pd.DataFrame:
    """构造含缺失资格、股票池变化和行业控制变量的乱序面板。"""
    codes = np.array([f"S{index}" for index in range(6)])
    dates = pd.date_range("2021-01-04", periods=10, freq="B")
    rows: list[dict[str, object]] = []
    for date_index, current_date in enumerate(dates):
        for code_index, code in enumerate(codes):
            active: bool | None = (date_index + code_index) % 5 != 0
            if date_index == 4 and code_index == 2:
                active = None
            rows.append(
                {
                    "time": current_date,
                    "code": code,
                    "close": 20.0 + code_index * 2.3 + date_index * 0.7 + np.sin(date_index + code_index),
                    "volume": 0.0 if (date_index * 2 + code_index) % 11 == 0 else 1000.0 + 13 * date_index + code_index,
                    "active": active,
                    "industry": ("bank", "energy", "tech")[code_index % 3],
                    "size": np.exp(4.0 + code_index * 0.18 + date_index * 0.025),
                }
            )
    source = pd.DataFrame(rows)
    order = np.random.default_rng(202104).permutation(len(source))
    return source.iloc[order].reset_index(drop=True)


def test_named_dependencies_compose_ts_and_cs_on_unsorted_panel(ddb_session: Any) -> None:
    """反向声明的命名因子按依赖递归计算，并保持筛选、分组、排序和回填语义。"""
    source = _pipeline_source()
    positive_volume = direct("binary.gt", {"left": "volume", "right": 0})
    non_null_neutral = direct("unary.not_null", {"col": "neutral"})
    non_null_return = direct("unary.not_null", {"col": "rolling_return"})
    definitions = {
        "score": cross_section(
            "unary.zscore",
            {"col": "neutral"},
            {"ddof": 0},
            on=non_null_neutral,
        ),
        "neutral": cross_section(
            "controls.neutralize_by",
            {"target": "rolling_return", "controls": ["industry", "log_size"]},
            {"intercept": True},
            on=non_null_return,
        ),
        "rolling_return": time_series(
            "unary.rolling_mean",
            {"col": "one_day_return"},
            {"window": 3, "min_periods": 2},
            on="eligible",
        ),
        "one_day_return": time_series(
            "unary.pct_change",
            {"col": "close"},
            {"periods": 1},
            on="eligible",
        ),
        "log_size": direct("unary.log", {"col": "size"}),
        "eligible": direct(
            "binary.and",
            {"left": "active", "right": positive_volume},
        ),
    }

    active = source["active"].astype("boolean")
    eligible = active & source["volume"].gt(0).astype("boolean")
    selected = bool_mask(eligible, source.index)
    expected_return = apply_time_series(
        source,
        selected,
        lambda group: group["close"] / group["close"].shift(1) - 1,
    )
    working = source.assign(one_day_return=expected_return)
    expected_rolling = apply_time_series(
        working,
        selected,
        lambda group: group["one_day_return"].rolling(3, min_periods=2).mean(),
    )
    working = working.assign(
        rolling_return=expected_rolling,
        log_size=np.log(source["size"]),
    )
    valid_return = expected_rolling.notna()
    expected_neutral = apply_cross_section(
        working,
        valid_return,
        lambda group: neutralize(
            group["rolling_return"],
            group[["industry", "log_size"]],
            intercept=True,
        ),
    )
    working = working.assign(neutral=expected_neutral)
    expected_score = apply_cross_section(
        working,
        expected_neutral.notna(),
        lambda group: zscore(group["neutral"], ddof=0),
    )

    result = compute_factors(ddb_session, source, definitions)
    pd.testing.assert_frame_equal(
        result[list(source.columns)],
        source,
        check_dtype=False,
    )
    assert_vector_equal(result["eligible"], eligible)
    assert_vector_equal(result["log_size"], np.log(source["size"]))
    assert_vector_equal(result["one_day_return"], expected_return)
    assert_vector_equal(result["rolling_return"], expected_rolling)
    assert_vector_equal(result["neutral"], expected_neutral, atol=1e-8, rtol=1e-8)
    assert_vector_equal(result["score"], expected_score, atol=1e-8, rtol=1e-8)


def test_index_value_factor_excludes_st_then_neutralizes_and_scores(
    ddb_session: Any,
) -> None:
    """指数价值因子按成分、ST、有效值筛选，并完成缩尾、中性化和残差标准化。"""
    dates = pd.to_datetime(["2024-06-28", "2024-07-01"])
    rows: list[dict[str, object]] = []
    for date_index, current_date in enumerate(dates):
        for code_index in range(12):
            pb = 0.8 + code_index * 0.23 + date_index * 0.07
            if code_index == 9:
                pb *= 4
            if (date_index, code_index) in {(0, 4), (1, 8)}:
                pb = np.nan
            weight = 0.0 if (date_index, code_index) in {(0, 5), (1, 2)} else 1.0
            is_st = 1.0 if (date_index, code_index) in {(0, 3), (1, 7)} else 0.0
            if (date_index, code_index) == (0, 10):
                is_st = np.nan
            rows.append(
                {
                    "time": current_date,
                    "code": f"S{code_index:02d}",
                    "pb": pb,
                    "circ_mv": np.exp(4.0 + code_index * 0.11 + date_index * 0.03),
                    "industry": None if code_index == 11 else (
                        "bank",
                        "energy",
                        "tech",
                    )[code_index % 3],
                    "is_st": is_st,
                    "weight_000300SH": weight,
                }
            )
    source = pd.DataFrame(rows).sample(frac=1, random_state=202407).reset_index(drop=True)

    member = direct(
        "binary.gt",
        {"left": "weight_000300SH", "right": 0},
    )
    non_st = direct("binary.eq", {"left": "is_st", "right": 0})
    definitions = {
        "score": cross_section(
            "unary.zscore",
            {"col": "neutral_pb"},
            {"ddof": 0},
            on=direct("unary.not_null", {"col": "neutral_pb"}),
        ),
        "neutral_pb": cross_section(
            "controls.neutralize_by",
            {
                "target": "winsor_pb",
                "controls": ["industry", "log_circ_mv"],
            },
            {"intercept": True},
            on=direct(
                "binary.and",
                {
                    "left": "eligible",
                    "right": direct("unary.not_null", {"col": "winsor_pb"}),
                },
            ),
        ),
        "winsor_pb": cross_section(
            "unary.winsorize",
            {"col": "pb"},
            {"lower": 0.1, "upper": 0.9},
            on=direct(
                "binary.and",
                {
                    "left": "eligible",
                    "right": direct("unary.not_null", {"col": "pb"}),
                },
            ),
        ),
        "log_circ_mv": direct("unary.log", {"col": "circ_mv"}),
        "eligible": direct(
            "binary.and",
            {"left": member, "right": non_st},
        ),
    }

    nullable_weight = source["weight_000300SH"].astype("Float64")
    nullable_st = source["is_st"].astype("Float64")
    eligible = nullable_weight.gt(0) & nullable_st.eq(0)
    valid_pb = bool_mask(eligible & source["pb"].notna(), source.index)

    def winsorize(group: pd.DataFrame) -> pd.Series:
        """按当前有效股票池的 10%/90% 分位数缩尾。"""
        lower = group["pb"].quantile(0.1)
        upper = group["pb"].quantile(0.9)
        return group["pb"].clip(lower, upper)

    expected_winsor = apply_cross_section(source, valid_pb, winsorize)
    working = source.assign(
        winsor_pb=expected_winsor,
        log_circ_mv=np.log(source["circ_mv"]),
    )
    valid_winsor = bool_mask(
        eligible & expected_winsor.notna(),
        source.index,
    )
    expected_neutral = apply_cross_section(
        working,
        valid_winsor,
        lambda group: neutralize(
            group["winsor_pb"],
            group[["industry", "log_circ_mv"]],
            intercept=True,
        ),
    )
    working = working.assign(neutral_pb=expected_neutral)
    expected_score = apply_cross_section(
        working,
        expected_neutral.notna(),
        lambda group: zscore(group["neutral_pb"], ddof=0),
    )

    result = compute_factors(ddb_session, source, definitions)
    assert_vector_equal(result["eligible"], eligible)
    assert_vector_equal(result["log_circ_mv"], working["log_circ_mv"])
    assert_vector_equal(result["winsor_pb"], expected_winsor)
    assert_vector_equal(result["neutral_pb"], expected_neutral, atol=1e-8, rtol=1e-8)
    assert_vector_equal(result["score"], expected_score, atol=1e-8, rtol=1e-8)


def test_financial_rolling_mean_uses_only_changed_report_rows(
    ddb_session: Any,
) -> None:
    """财报前填后的日频序列只在数值变化日进入报告期滚动窗口。"""
    dates = pd.date_range("2024-01-02", periods=8, freq="B")
    source = pd.DataFrame(
        {
            "time": list(dates) * 2,
            "code": ["A"] * 8 + ["B"] * 8,
            "total_assets": [
                np.nan,
                100.0,
                100.0,
                110.0,
                110.0,
                90.0,
                90.0,
                120.0,
                np.nan,
                np.nan,
                200.0,
                200.0,
                210.0,
                210.0,
                230.0,
                230.0,
            ],
        }
    ).sample(frac=1, random_state=202401).reset_index(drop=True)
    definitions = {
        "report_average": time_series(
            "unary.rolling_mean",
            {"col": "total_assets"},
            {"window": 3, "min_periods": 2},
            on="asset_changed",
        ),
        "asset_changed": time_series(
            "unary.changed",
            {"col": "total_assets"},
            {"null_equal": True},
            on=direct("unary.not_null", {"col": "total_assets"}),
        ),
    }

    def changed(group: pd.DataFrame) -> pd.Series:
        """第一份有效报告视为变化，后续仅比较相邻有效报告值。"""
        result = group["total_assets"].ne(group["total_assets"].shift(1))
        result.iloc[0] = True
        return result

    expected_changed = apply_time_series(
        source,
        source["total_assets"].notna(),
        changed,
        dtype="object",
    )
    expected_average = apply_time_series(
        source,
        expected_changed,
        lambda group: group["total_assets"].rolling(
            3,
            min_periods=2,
        ).mean(),
    )

    result = compute_factors(ddb_session, source, definitions)
    assert_vector_equal(result["asset_changed"], expected_changed)
    assert_vector_equal(result["report_average"], expected_average)


def test_momentum_skips_ineligible_rows_then_ranks_each_cross_section(
    ddb_session: Any,
) -> None:
    """出池、ST 和价格缺失日不进入收益率序列，恢复后使用上一有效观测并参与当日排名。"""
    dates = pd.date_range("2024-03-01", periods=6, freq="B")
    close = {
        "A": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0],
        "B": [20.0, 20.0, 22.0, 21.0, 23.0, 24.0],
        "C": [30.0, np.nan, 31.0, 32.0, 33.0, 34.0],
    }
    rows: list[dict[str, object]] = []
    for code in ("A", "B", "C"):
        for date_index, current_date in enumerate(dates):
            rows.append(
                {
                    "time": current_date,
                    "code": code,
                    "close": close[code][date_index],
                    "weight_000300SH": (
                        0.0 if code == "A" and date_index == 2 else 1.0
                    ),
                    "is_st": 1.0 if code == "B" and date_index == 3 else 0.0,
                }
            )
    source = pd.DataFrame(rows).sample(frac=1, random_state=202403).reset_index(drop=True)
    member = direct(
        "binary.gt",
        {"left": "weight_000300SH", "right": 0},
    )
    non_st = direct("binary.eq", {"left": "is_st", "right": 0})
    definitions = {
        "momentum_rank": cross_section(
            "unary.rank",
            {"col": "momentum"},
            {"ascending": False, "ties_method": "average"},
            on=direct("unary.not_null", {"col": "momentum"}),
        ),
        "momentum": time_series(
            "unary.pct_change",
            {"col": "close"},
            {"periods": 1},
            on="tradable",
        ),
        "tradable": direct(
            "binary.and",
            {
                "left": direct(
                    "binary.and",
                    {"left": member, "right": non_st},
                ),
                "right": direct("unary.not_null", {"col": "close"}),
            },
        ),
    }

    tradable = (
        source["weight_000300SH"].gt(0)
        & source["is_st"].eq(0)
        & source["close"].notna()
    )
    expected_momentum = apply_time_series(
        source,
        tradable,
        lambda group: group["close"] / group["close"].shift(1) - 1,
    )
    working = source.assign(momentum=expected_momentum)
    expected_rank = apply_cross_section(
        working,
        expected_momentum.notna(),
        lambda group: group["momentum"].rank(
            method="average",
            ascending=False,
        ),
    )

    result = compute_factors(ddb_session, source, definitions)
    assert_vector_equal(result["tradable"], tradable)
    assert_vector_equal(result["momentum"], expected_momentum)
    assert_vector_equal(result["momentum_rank"], expected_rank)

    indexed = result.set_index(["code", "time"])
    np.testing.assert_allclose(indexed.loc[("A", dates[3]), "momentum"], 13 / 11 - 1)
    np.testing.assert_allclose(indexed.loc[("B", dates[4]), "momentum"], 23 / 22 - 1)
    np.testing.assert_allclose(indexed.loc[("C", dates[2]), "momentum"], 31 / 30 - 1)
