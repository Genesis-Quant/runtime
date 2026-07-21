"""验证全算符退化路径及跨类别嵌套 DSL 的端到端语义。"""

from typing import Any

import numpy as np
import pandas as pd
import pytest

from core.operators import Derivative
from core.operators.base import DirectOperator
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
