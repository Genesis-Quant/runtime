"""使用明确的输入表和期望向量验证复杂 DSL 端到端计算。"""

from dataclasses import dataclass
import json
from typing import Any

import numpy as np
import pandas as pd
import pytest

from core.operators import Derivative


def _node(
    node_type: str,
    operation: str,
    fields: dict[str, Any],
    params: dict[str, Any] | None = None,
    *,
    on: object | None = None,
) -> dict[str, Any]:
    """构造一个用于执行测试的 DSL 节点。"""
    result: dict[str, Any] = {
        "type": node_type,
        "op": operation,
        "fields": fields,
        "params": {} if params is None else params,
    }
    if node_type != "DIRECT":
        result["on"] = on
    return result


def _direct(
    operation: str,
    fields: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 DIRECT 类型的测试节点。"""
    return _node("DIRECT", operation, fields, params)


def _time_series(
    operation: str,
    fields: dict[str, Any],
    params: dict[str, Any] | None = None,
    *,
    on: object,
) -> dict[str, Any]:
    """构造带 on 条件的 TS 测试节点。"""
    return _node("TS", operation, fields, params, on=on)


def _cross_section(
    operation: str,
    fields: dict[str, Any],
    params: dict[str, Any] | None = None,
    *,
    on: object,
) -> dict[str, Any]:
    """构造带 on 条件的 CS 测试节点。"""
    return _node("CS", operation, fields, params, on=on)


TRUE_NODE = _direct("nullary.true", {})
NAN = float("nan")


@dataclass(frozen=True, slots=True)
class ComplexExecutionCase:
    """一张输入表、一组 DSL 定义及人工计算的期望列。"""

    name: str
    source: dict[str, list[Any]]
    definitions: dict[str, dict[str, Any]]
    expected: dict[str, list[Any]]


COMPLEX_EXECUTION_CASES = (
    ComplexExecutionCase(
        name="逐行收益清洗与条件选择",
        source={
            "time": ["2024-01-02"] * 6,
            "code": ["A", "B", "C", "D", "E", "F"],
            "open": [10.0, 10.0, 0.0, 20.0, NAN, 5.0],
            "close": [12.0, 8.0, 3.0, 25.0, 7.0, 5.0],
            "active": [True, True, True, False, True, True],
        },
        definitions={
            "raw_return": _direct(
                "binary.div",
                {
                    "left": _direct(
                        "binary.sub",
                        {"left": "close", "right": "open"},
                    ),
                    "right": "open",
                },
            ),
            "clean_return": _direct(
                "multiary.coalesce",
                {"cols": ["raw_return", 0.0]},
            ),
            "signal": _direct(
                "multiary.and",
                {
                    "cols": [
                        "active",
                        _direct(
                            "binary.gt",
                            {"left": "clean_return", "right": 0.0},
                        ),
                    ]
                },
            ),
            "selected_return": _direct(
                "ternary.where",
                {
                    "condition": "signal",
                    "if_true": "clean_return",
                    "if_false": 0.0,
                },
            ),
        },
        expected={
            "raw_return": [0.2, -0.2, NAN, 0.25, NAN, 0.0],
            "clean_return": [0.2, -0.2, 0.0, 0.25, 0.0, 0.0],
            "signal": [True, False, False, False, False, False],
            "selected_return": [0.2, 0.0, 0.0, 0.0, 0.0, 0.0],
        },
    ),
    ComplexExecutionCase(
        name="on排除样本后的分股票滚动均值",
        source={
            "time": [
                "2024-01-01", "2024-01-01",
                "2024-01-02", "2024-01-02",
                "2024-01-03", "2024-01-03",
                "2024-01-04", "2024-01-04",
                "2024-01-05", "2024-01-05",
            ],
            "code": ["A", "B"] * 5,
            "x": [1.0, 10.0, 2.0, 20.0, 3.0, 30.0, 4.0, 40.0, 5.0, 50.0],
            "eligible": [True, True, False, True, True, False, True, True, False, True],
        },
        definitions={
            "rolling_x": _time_series(
                "unary.rolling_mean",
                {"col": "x"},
                {"window": 3, "min_periods": 2},
                on="eligible",
            )
        },
        expected={
            "rolling_x": [NAN, NAN, NAN, 15.0, 2.0, NAN, 8.0 / 3.0, 70.0 / 3.0, NAN, 110.0 / 3.0]
        },
    ),
    ComplexExecutionCase(
        name="股票池内截面标准化及零方差",
        source={
            "time": ["2024-01-01"] * 4 + ["2024-01-02"] * 4 + ["2024-01-03"] * 4,
            "code": ["A", "B", "C", "D"] * 3,
            "x": [1.0, 2.0, 3.0, 100.0, 5.0, 5.0, 9.0, 11.0, 1.0, 3.0, 5.0, 7.0],
            "membership": [True, True, True, False, True, True, False, False, False, True, True, True],
        },
        definitions={
            "zscore_x": _cross_section(
                "unary.zscore",
                {"col": "x"},
                {"ddof": 0},
                on="membership",
            )
        },
        expected={
            "zscore_x": [
                -np.sqrt(1.5), 0.0, np.sqrt(1.5), NAN,
                NAN, NAN, NAN, NAN,
                NAN, -np.sqrt(1.5), 0.0, np.sqrt(1.5),
            ]
        },
    ),
    ComplexExecutionCase(
        name="行业分组截面去均值",
        source={
            "time": ["2024-01-01"] * 6 + ["2024-01-02"] * 6,
            "code": ["A", "B", "C", "D", "E", "F"] * 2,
            "industry": ["I1", "I1", "I2", "I2", "I3", "I3"] * 2,
            "x": [1.0, 3.0, 10.0, 14.0, 7.0, 7.0, 2.0, 8.0, 4.0, 4.0, 1.0, 9.0],
            "membership": [True] * 6 + [True, False, True, True, True, True],
        },
        definitions={
            "industry_demean": _cross_section(
                "grouped.demean",
                {"col": "x", "by": "industry"},
                on="membership",
            )
        },
        expected={
            "industry_demean": [-1.0, 1.0, -2.0, 2.0, 0.0, 0.0, 0.0, NAN, 0.0, 0.0, -4.0, 4.0]
        },
    ),
    ComplexExecutionCase(
        name="行业与连续变量OLS中性化",
        source={
            "time": ["2024-01-01"] * 6 + ["2024-01-02"] * 6,
            "code": ["A", "B", "C", "D", "E", "F"] * 2,
            "industry": ["I1", "I1", "I1", "I2", "I2", "I2"] * 2,
            "size": [1.0, 2.0, 3.0, 1.0, 2.0, 3.0] * 2,
            "factor": [12.0, 14.0, 16.0, 17.0, 19.0, 21.0, 13.0, 12.0, 17.0, 16.0, 21.0, 20.0],
        },
        definitions={
            "neutral_factor": _cross_section(
                "controls.neutralize_by",
                {"target": "factor", "controls": ["industry", "size"]},
                {"intercept": True},
                on=TRUE_NODE,
            )
        },
        expected={
            "neutral_factor": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, -2.0, 1.0, -1.0, 2.0, -1.0]
        },
    ),
    ComplexExecutionCase(
        name="时序差分再做截面去均值",
        source={
            "time": ["2024-01-01"] * 3 + ["2024-01-02"] * 3 + ["2024-01-03"] * 3,
            "code": ["A", "B", "C"] * 3,
            "x": [1.0, 10.0, 5.0, 3.0, 11.0, 9.0, 6.0, 15.0, 10.0],
        },
        definitions={
            "change": _time_series(
                "unary.diff",
                {"col": "x"},
                {"periods": 1},
                on=TRUE_NODE,
            ),
            "relative_change": _cross_section(
                "unary.demean",
                {"col": "change"},
                on=_direct("unary.not_null", {"col": "change"}),
            ),
        },
        expected={
            "change": [NAN, NAN, NAN, 2.0, 1.0, 4.0, 3.0, 4.0, 1.0],
            "relative_change": [NAN, NAN, NAN, -1.0 / 3.0, -4.0 / 3.0, 5.0 / 3.0, 1.0 / 3.0, 4.0 / 3.0, -5.0 / 3.0],
        },
    ),
    ComplexExecutionCase(
        name="仅在财报变更时计算两期资产均值",
        source={
            "time": [
                "2024-03-31", "2024-03-31",
                "2024-06-30", "2024-06-30",
                "2024-09-30", "2024-09-30",
                "2024-12-31", "2024-12-31",
                "2025-03-31", "2025-03-31",
            ],
            "code": ["A", "B"] * 5,
            "asset": [100.0, 200.0, 100.0, 200.0, 120.0, 200.0, 120.0, 210.0, 150.0, 210.0],
            "report": [True, True, False, False, True, True, False, True, True, False],
        },
        definitions={
            "asset_average": _time_series(
                "unary.rolling_mean",
                {"col": "asset"},
                {"window": 2, "min_periods": 2},
                on=_time_series(
                    "unary.changed",
                    {"col": "asset"},
                    {"null_equal": True},
                    on="report",
                ),
            )
        },
        expected={
            "asset_average": [NAN, NAN, NAN, NAN, 110.0, NAN, NAN, 205.0, 135.0, NAN]
        },
    ),
    ComplexExecutionCase(
        name="股票池ST与流动性条件控制截面",
        source={
            "time": ["2024-01-02"] * 5,
            "code": ["A", "B", "C", "D", "E"],
            "x": [10.0, 20.0, 30.0, 40.0, 50.0],
            "membership": [True, True, True, False, True],
            "st": [0, 1, 0, 0, 0],
            "liquid": [True, True, False, True, True],
        },
        definitions={
            "eligible": _direct(
                "multiary.and",
                {
                    "cols": [
                        "membership",
                        _direct("binary.eq", {"left": "st", "right": 0}),
                        "liquid",
                    ]
                },
            ),
            "filtered_demean": _cross_section(
                "unary.demean",
                {"col": "x"},
                on="eligible",
            ),
        },
        expected={
            "eligible": [True, False, False, False, True],
            "filtered_demean": [-20.0, NAN, NAN, NAN, 20.0],
        },
    ),
    ComplexExecutionCase(
        name="分股票限次前向填充并恢复mask",
        source={
            "time": [
                "2024-01-01", "2024-01-01",
                "2024-01-02", "2024-01-02",
                "2024-01-03", "2024-01-03",
                "2024-01-04", "2024-01-04",
                "2024-01-05", "2024-01-05",
            ],
            "code": ["A", "B"] * 5,
            "x": [1.0, NAN, NAN, 2.0, NAN, NAN, 4.0, NAN, NAN, 5.0],
            "active": [True, True, True, True, False, True, True, True, True, True],
        },
        definitions={
            "filled": _time_series(
                "unary.ffill",
                {"col": "x"},
                {"limit": 1},
                on="active",
            )
        },
        expected={
            "filled": [1.0, NAN, 1.0, 2.0, NAN, 2.0, 4.0, NAN, 4.0, 5.0]
        },
    ),
    ComplexExecutionCase(
        name="TA均线只使用on内有效观测",
        source={
            "time": [
                "2024-01-01", "2024-01-01",
                "2024-01-02", "2024-01-02",
                "2024-01-03", "2024-01-03",
                "2024-01-04", "2024-01-04",
                "2024-01-05", "2024-01-05",
                "2024-01-06", "2024-01-06",
            ],
            "code": ["A", "B"] * 6,
            "close": [1.0, 10.0, 2.0, 20.0, 3.0, 30.0, 4.0, 40.0, 5.0, 50.0, 6.0, 60.0],
            "active": [True, True, True, False, False, True, True, True, True, False, True, True],
        },
        definitions={
            "sma3": _time_series(
                "talib.sma",
                {"col": "close"},
                {"time_period": 3},
                on="active",
            )
        },
        expected={
            "sma3": [NAN, NAN, NAN, NAN, NAN, NAN, 7.0 / 3.0, 80.0 / 3.0, 11.0 / 3.0, NAN, 5.0, 130.0 / 3.0]
        },
    ),
)


def _validated_definitions(
    definitions: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """使用实际入口模型校验并展开全部默认参数。"""
    return {
        name: Derivative.model_validate(definition).model_dump(mode="json")
        for name, definition in definitions.items()
    }


@pytest.mark.parametrize(
    "case",
    COMPLEX_EXECUTION_CASES,
    ids=lambda case: case.name,
)
def test_complex_dsl_execution(ddb_session, case: ComplexExecutionCase) -> None:
    """复杂 DSL 对明确测试数据的输出应与人工期望一致。"""
    source = pd.DataFrame(case.source)
    source["time"] = pd.to_datetime(source["time"])
    definitions = _validated_definitions(case.definitions)
    definitions_json = json.dumps(
        definitions,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    ddb_session.upload({"complex_source": source})
    result = ddb_session.run(
        "compute_factors(complex_source, fromStdJson("
        f"{json.dumps(definitions_json, ensure_ascii=False)}))"
    )

    assert len(result) == len(source)
    assert result["code"].tolist() == source["code"].tolist()
    for factor, values in case.expected.items():
        pd.testing.assert_series_equal(
            result[factor].reset_index(drop=True),
            pd.Series(values),
            check_dtype=False,
            check_names=False,
            check_exact=False,
            rtol=1e-9,
            atol=1e-9,
        )
