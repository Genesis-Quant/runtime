"""验证复杂派生因子 JSON 的模型构造结果。"""

from collections import Counter
from dataclasses import dataclass
import json
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from core.operators import Derivative


_MISSING = object()
Path = tuple[str | int, ...]


def _node(
    node_type: str,
    operation: str,
    fields: dict[str, Any],
    params: dict[str, Any] | None = None,
    *,
    on: object = _MISSING,
) -> dict[str, Any]:
    """构造保留调用方显式字段的 DSL JSON 节点。"""
    result: dict[str, Any] = {
        "type": node_type,
        "op": operation,
        "fields": fields,
        "params": {} if params is None else params,
    }
    if on is not _MISSING:
        result["on"] = on
    return result


def _direct(
    operation: str,
    fields: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 DIRECT 节点。"""
    return _node("DIRECT", operation, fields, params)


def _time_series(
    operation: str,
    fields: dict[str, Any],
    params: dict[str, Any] | None = None,
    *,
    on: object = _MISSING,
) -> dict[str, Any]:
    """构造 TS 节点。"""
    return _node("TS", operation, fields, params, on=on)


def _cross_section(
    operation: str,
    fields: dict[str, Any],
    params: dict[str, Any] | None = None,
    *,
    on: object = _MISSING,
) -> dict[str, Any]:
    """构造 CS 节点。"""
    return _node("CS", operation, fields, params, on=on)


TRUE_NODE = _direct("nullary.true", {})


@dataclass(frozen=True, slots=True)
class ConstructionCase:
    """一个复杂合法 DSL 的预期构造结果。"""

    name: str
    payload: dict[str, Any]
    model_name: str
    fields_name: str
    params_name: str
    operations: tuple[str, ...]
    defaults: tuple[tuple[Path, object], ...] = ()


VALID_CASES = (
    ConstructionCase(
        name="多条件直接筛选",
        payload=_direct(
            "multiary.and",
            {
                "cols": [
                    _direct("binary.gt", {"left": "pe", "right": 0}),
                    _direct(
                        "unary.not",
                        {
                            "col": _direct(
                                "unary.is_null",
                                {"col": "market_value"},
                            )
                        },
                    ),
                    _direct(
                        "unary.between",
                        {"col": "turnover"},
                        {"lower": 0.0, "upper": 1.0},
                    ),
                ]
            },
        ),
        model_name="DirectMultiaryAndOperator",
        fields_name="MultiaryFields",
        params_name="DirectMultiaryAndParams",
        operations=(
            "multiary.and",
            "binary.gt",
            "unary.not",
            "unary.is_null",
            "unary.between",
        ),
        defaults=((('fields', 'cols', 2, 'params', 'inclusive'), "both"),),
    ),
    ConstructionCase(
        name="收益率滚动均值与复合on",
        payload=_time_series(
            "unary.rolling_mean",
            {
                "col": _direct(
                    "binary.div",
                    {
                        "left": _direct(
                            "binary.sub",
                            {"left": "close", "right": "open"},
                        ),
                        "right": "open",
                    },
                )
            },
            {"window": 20},
            on=_direct(
                "multiary.and",
                {
                    "cols": [
                        _direct("binary.gt", {"left": "volume", "right": 0}),
                        _direct("unary.not_null", {"col": "close"}),
                    ]
                },
            ),
        ),
        model_name="TimeSeriesUnaryRollingMeanOperator",
        fields_name="UnaryFields",
        params_name="TimeSeriesUnaryRollingMeanParams",
        operations=(
            "unary.rolling_mean",
            "binary.div",
            "binary.sub",
            "multiary.and",
            "binary.gt",
            "unary.not_null",
        ),
        defaults=((('params', 'min_periods'), None),),
    ),
    ConstructionCase(
        name="时序字段嵌套截面标准化",
        payload=_time_series(
            "unary.shift",
            {
                "col": _cross_section(
                    "unary.zscore",
                    {"col": "market_value"},
                    {"ddof": 0},
                    on=_direct("binary.gt", {"left": "pe", "right": 0}),
                )
            },
            on=TRUE_NODE,
        ),
        model_name="TimeSeriesUnaryShiftOperator",
        fields_name="UnaryFields",
        params_name="TimeSeriesUnaryShiftParams",
        operations=(
            "unary.shift",
            "unary.zscore",
            "binary.gt",
            "nullary.true",
        ),
        defaults=((('params', 'periods'), 1),),
    ),
    ConstructionCase(
        name="行业与对数市值中性化",
        payload=_cross_section(
            "controls.neutralize_by",
            {
                "target": _cross_section(
                    "unary.winsorize_mad",
                    {"col": "factor"},
                    {"n": 4.0},
                    on="membership",
                ),
                "controls": [
                    "industry",
                    _direct("unary.log", {"col": "market_value"}),
                ],
            },
            on=_time_series(
                "unary.changed",
                {"col": "membership"},
                {"null_equal": True},
                on=TRUE_NODE,
            ),
        ),
        model_name="CrossSectionControlsNeutralizeByOperator",
        fields_name="ControlsFields",
        params_name="CrossSectionControlsNeutralizeByParams",
        operations=(
            "controls.neutralize_by",
            "unary.winsorize_mad",
            "unary.log",
            "unary.changed",
            "nullary.true",
        ),
        defaults=(
            (("fields", "target", "params", "scale"), 1.4826),
            (("params", "intercept"), True),
        ),
    ),
    ConstructionCase(
        name="财报更新序列的行业内标准化",
        payload=_cross_section(
            "grouped.zscore",
            {
                "col": _time_series(
                    "unary.rolling_mean",
                    {"col": "roe"},
                    {"window": 4},
                    on=_direct("unary.not_null", {"col": "roe"}),
                ),
                "by": "industry",
            },
            on="membership",
        ),
        model_name="CrossSectionGroupedZscoreOperator",
        fields_name="GroupedFields",
        params_name="CrossSectionGroupedZscoreParams",
        operations=(
            "grouped.zscore",
            "unary.rolling_mean",
            "unary.not_null",
        ),
        defaults=(
            (("fields", "col", "params", "min_periods"), None),
            (("params", "ddof"), 1),
        ),
    ),
    ConstructionCase(
        name="复权价格MACD输出选择",
        payload=_time_series(
            "talib.macd",
            {
                "col": _direct(
                    "binary.div",
                    {"left": "close_hfq", "right": "pre_close"},
                )
            },
            {"output": "hist"},
            on=_direct("binary.gt", {"left": "volume", "right": 0}),
        ),
        model_name="TimeSeriesTalibMacdOperator",
        fields_name="UnaryFields",
        params_name="TimeSeriesTalibMacdParams",
        operations=("talib.macd", "binary.div", "binary.gt"),
        defaults=(
            (("params", "fast_period"), 12),
            (("params", "slow_period"), 26),
            (("params", "signal_period"), 9),
        ),
    ),
    ConstructionCase(
        name="OHLCV资金流量指标",
        payload=_time_series(
            "talib.mfi",
            {
                "high": "high_hfq",
                "low": "low_hfq",
                "close": "close_hfq",
                "volume": "volume",
            },
            {"time_period": 14},
            on=_direct(
                "multiary.and",
                {
                    "cols": [
                        "membership",
                        _direct("binary.gt", {"left": "volume", "right": 0}),
                        _direct("unary.not_null", {"col": "close_hfq"}),
                    ]
                },
            ),
        ),
        model_name="TimeSeriesTalibMfiOperator",
        fields_name="OHLCVFields",
        params_name="TimeSeriesTalibMfiParams",
        operations=(
            "talib.mfi",
            "multiary.and",
            "binary.gt",
            "unary.not_null",
        ),
    ),
    ConstructionCase(
        name="截面排名后的指数加权均值",
        payload=_time_series(
            "unary.ewm_mean",
            {
                "col": _direct(
                    "unary.log1p",
                    {
                        "col": _cross_section(
                            "unary.rank_pct",
                            {"col": "amount"},
                            {"ascending": False},
                            on="membership",
                        )
                    },
                )
            },
            {
                "half_life": 10.0,
                "min_periods": 3,
                "adjust": False,
                "ignore_na": True,
            },
            on=_direct(
                "binary.gt",
                {
                    "left": _cross_section(
                        "unary.zscore",
                        {"col": "market_value"},
                        on="membership",
                    ),
                    "right": -2.0,
                },
            ),
        ),
        model_name="TimeSeriesUnaryEwmMeanOperator",
        fields_name="UnaryFields",
        params_name="TimeSeriesUnaryEwmMeanParams",
        operations=(
            "unary.ewm_mean",
            "unary.log1p",
            "unary.rank_pct",
            "binary.gt",
            "unary.zscore",
        ),
        defaults=(
            (("fields", "col", "fields", "col", "params", "ties_method"), "min"),
            (("params", "com"), None),
            (("params", "span"), None),
            (("params", "alpha"), None),
            (("on", "fields", "left", "params", "ddof"), 1),
        ),
    ),
    ConstructionCase(
        name="日期条件与类型化空值",
        payload=_direct(
            "ternary.where",
            {
                "condition": _direct(
                    "unary.between",
                    {"col": "trade_date"},
                    {"lower": 20240101.0, "upper": 20241231.0},
                ),
                "if_true": _direct(
                    "nullary.literal",
                    {},
                    {"value": "2024-12-31", "dtype": "date"},
                ),
                "if_false": _direct(
                    "nullary.literal",
                    {},
                    {"value": None, "dtype": "date"},
                ),
            },
        ),
        model_name="DirectTernaryWhereOperator",
        fields_name="TernaryFields",
        params_name="DirectTernaryWhereParams",
        operations=(
            "ternary.where",
            "unary.between",
            "nullary.literal",
            "nullary.literal",
        ),
        defaults=((('fields', 'condition', 'params', 'inclusive'), "both"),),
    ),
    ConstructionCase(
        name="时序超额收益的截面正态排名",
        payload=_cross_section(
            "unary.rank_normal",
            {
                "col": _direct(
                    "binary.sub",
                    {
                        "left": _time_series(
                            "unary.pct_change",
                            {"col": "close_hfq"},
                            {"periods": 5},
                            on=_direct(
                                "binary.gt",
                                {"left": "volume", "right": 0},
                            ),
                        ),
                        "right": _cross_section(
                            "unary.mean",
                            {"col": "return_5d"},
                            on="membership",
                        ),
                    },
                )
            },
            {"ascending": False},
            on=_direct(
                "multiary.and",
                {
                    "cols": [
                        "membership",
                        _direct("unary.not_null", {"col": "return_5d"}),
                    ]
                },
            ),
        ),
        model_name="CrossSectionUnaryRankNormalOperator",
        fields_name="UnaryFields",
        params_name="CrossSectionUnaryRankNormalParams",
        operations=(
            "unary.rank_normal",
            "binary.sub",
            "unary.pct_change",
            "binary.gt",
            "unary.mean",
            "multiary.and",
            "unary.not_null",
        ),
    ),
)


def _value_at(value: object, path: Path) -> object:
    """读取序列化结果中的嵌套值。"""
    current = value
    for part in path:
        current = current[part]  # type: ignore[index]
    return current


def _operator_names(value: object) -> list[str]:
    """收集构造结果中的全部具体算符。"""
    result: list[str] = []
    if isinstance(value, Derivative):
        result.append(value.op)
    if isinstance(value, BaseModel):
        for child in value.__dict__.values():
            result.extend(_operator_names(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            result.extend(_operator_names(child))
    return result


@pytest.mark.parametrize("case", VALID_CASES, ids=lambda case: case.name)
def test_complex_derivative_construction(case: ConstructionCase) -> None:
    """复杂 JSON 应构造成正确模型并按预期展开默认值。"""
    result = Derivative.model_validate_json(
        json.dumps(case.payload, ensure_ascii=False, separators=(",", ":"))
    )

    assert type(result).__name__ == case.model_name
    assert type(result.fields).__name__ == case.fields_name
    assert type(result.params).__name__ == case.params_name
    assert result.model_dump(mode="json", exclude_unset=True) == case.payload
    assert Counter(_operator_names(result)) == Counter(case.operations)

    complete = result.model_dump(mode="json")
    for path, expected in case.defaults:
        assert _value_at(complete, path) == expected


@dataclass(frozen=True, slots=True)
class InvalidConstructionCase:
    """一个复杂非法 DSL 及其预期错误。"""

    name: str
    payload: dict[str, Any]
    location_prefix: Path
    message: str


INVALID_CASES = (
    InvalidConstructionCase(
        "DIRECT禁止on",
        {**_direct("binary.add", {"left": "x", "right": 1}), "on": TRUE_NODE},
        ("on",),
        "Extra inputs are not permitted",
    ),
    InvalidConstructionCase(
        "TS缺少on",
        _time_series("unary.rolling_mean", {"col": "x"}, {"window": 5}),
        ("on",),
        "Field required",
    ),
    InvalidConstructionCase(
        "CS缺少on",
        _cross_section("unary.zscore", {"col": "x"}),
        ("on",),
        "Field required",
    ),
    InvalidConstructionCase(
        "on嵌套数值算符",
        _time_series(
            "unary.shift",
            {"col": "x"},
            on=_direct("binary.add", {"left": "x", "right": 1}),
        ),
        (),
        "on 嵌套表达式必须返回 BOOL",
    ),
    InvalidConstructionCase(
        "on直接传布尔常量",
        _time_series("unary.shift", {"col": "x"}, on=True),
        ("on",),
        "Derivative 必须是 JSON 对象，当前类型为 bool",
    ),
    InvalidConstructionCase(
        "滚动最少样本超过窗口",
        _time_series(
            "unary.rolling_mean",
            {"col": "x"},
            {"window": 5, "min_periods": 6},
            on=TRUE_NODE,
        ),
        ("params",),
        "params.min_periods 不能大于 params.window",
    ),
    InvalidConstructionCase(
        "EWM同时提供多个衰减参数",
        _time_series(
            "unary.ewm_mean",
            {"col": "x"},
            {"com": 1.0, "alpha": 0.5},
            on=TRUE_NODE,
        ),
        ("params",),
        "params.com/span/half_life/alpha 必须且只能提供一个",
    ),
    InvalidConstructionCase(
        "中性化缺少控制变量",
        _cross_section(
            "controls.neutralize_by",
            {"target": "x", "controls": []},
            on=TRUE_NODE,
        ),
        ("fields", "controls"),
        "List should have at least 1 item after validation",
    ),
    InvalidConstructionCase(
        "截面分组键使用列表",
        _cross_section(
            "grouped.zscore",
            {"col": "x", "by": []},
            on=TRUE_NODE,
        ),
        ("fields", "by"),
        "Derivative 必须是 JSON 对象，当前类型为 list",
    ),
    InvalidConstructionCase(
        "控制变量嵌套未知算符",
        _cross_section(
            "controls.neutralize_by",
            {
                "target": "x",
                "controls": [
                    _direct("binary.unknown", {"left": "a", "right": "b"})
                ],
            },
            on=TRUE_NODE,
        ),
        ("fields", "controls", 0),
        "不存在算符 'binary.unknown'",
    ),
    InvalidConstructionCase(
        "时间戳毫秒位数错误",
        _direct(
            "nullary.literal",
            {},
            {"value": "2024-01-01T00:00:00.12", "dtype": "timestamp"},
        ),
        ("params",),
        "YYYY-MM-DDTHH:MM:SS 或带三位毫秒",
    ),
    InvalidConstructionCase(
        "TA参数包含未知字段",
        _time_series(
            "talib.macd",
            {"col": "close"},
            {"fast_period": 12, "slow_period": 26, "unexpected": 1},
            on=TRUE_NODE,
        ),
        ("params", "unexpected"),
        "Extra inputs are not permitted",
    ),
    InvalidConstructionCase(
        "算符类别与type冲突",
        _node(
            "CS",
            "unary.rolling_mean",
            {"col": "x"},
            {"window": 5},
            on=TRUE_NODE,
        ),
        ("type",),
        "Input should be 'TS'",
    ),
    InvalidConstructionCase(
        "多元算符没有操作数",
        _direct("multiary.add", {"cols": []}),
        ("fields", "cols"),
        "List should have at least 1 item after validation",
    ),
)


@pytest.mark.parametrize("case", INVALID_CASES, ids=lambda case: case.name)
def test_complex_derivative_construction_error(
    case: InvalidConstructionCase,
) -> None:
    """复杂非法 JSON 应返回可定位的构造错误。"""
    payload = json.dumps(case.payload, ensure_ascii=False, separators=(",", ":"))

    with pytest.raises(ValidationError) as caught:
        Derivative.model_validate_json(payload)

    assert any(
        tuple(error["loc"][: len(case.location_prefix)]) == case.location_prefix
        and case.message in error["msg"]
        for error in caught.value.errors(include_url=False)
    ), caught.value

