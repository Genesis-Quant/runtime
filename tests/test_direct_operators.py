"""使用 NumPy/Pandas 独立结果逐个验证全部 DIRECT 算符。"""

from collections.abc import Callable
from dataclasses import dataclass
import operator

import numpy as np
import pandas as pd
import pytest

from core.query.operator import Derivative
from core.query.operator.base import DirectOperator
from tests.support.assertions import assert_vector_equal
from tests.support.dsl import compute_factors, direct


@dataclass(frozen=True)
class DirectContract:
    """保存单个 DIRECT 算符的完整 DSL 和独立期望结果。"""

    definition: dict[str, object]
    expected: object


def _missing(value: object) -> bool:
    """判断 Python 参考值是否代表 DolphinDB NULL。"""
    return bool(pd.isna(value))


def _arithmetic(
    left: pd.Series,
    right: pd.Series,
    function: Callable[[float, float], float],
    *,
    zero_is_null: bool = False,
) -> list[float]:
    """按 DolphinDB 二元算术的 NULL 传播规则计算参考值。"""
    result: list[float] = []
    for lhs, rhs in zip(left, right, strict=True):
        if _missing(lhs) or _missing(rhs) or (zero_is_null and rhs == 0):
            result.append(np.nan)
        else:
            result.append(function(float(lhs), float(rhs)))
    return result


def _comparison(
    left: pd.Series,
    right: pd.Series,
    function: Callable[[float, float], bool],
) -> list[bool | None]:
    """按任一操作数缺失就传播 NULL 的规则计算比较。"""
    result: list[bool | None] = []
    for lhs, rhs in zip(left, right, strict=True):
        if _missing(lhs) or _missing(rhs):
            result.append(None)
        else:
            result.append(bool(function(float(lhs), float(rhs))))
    return result


def _logical(
    left: pd.Series,
    right: pd.Series,
    function: Callable[[bool, bool], bool],
) -> list[bool | None]:
    """按二元 BOOL 算符任一输入为 NULL 就传播 NULL 的规则计算。"""
    result: list[bool | None] = []
    for lhs, rhs in zip(left, right, strict=True):
        if _missing(lhs) or _missing(rhs):
            result.append(None)
        else:
            result.append(bool(function(bool(lhs), bool(rhs))))
    return result


def _row_boolean(frame: pd.DataFrame, *, mode: str) -> list[bool | None]:
    """逐行执行 BOOL 归约，任一操作数缺失时传播 NULL。"""
    result: list[bool | None] = []
    for row in frame.itertuples(index=False, name=None):
        if any(_missing(value) for value in row):
            result.append(None)
        elif mode == "and":
            result.append(all(bool(value) for value in row))
        else:
            result.append(any(bool(value) for value in row))
    return result


@pytest.fixture(scope="module")
def direct_source() -> pd.DataFrame:
    """构造覆盖 NULL、零、无穷、日历边界和并列值的十二行输入。"""
    return pd.DataFrame(
        {
            "left": [1.0, 2.0, -3.0, 4.0, 0.0, 5.0, np.nan, -2.0, 3.0, 8.0, -4.0, np.nan],
            "right": [1.0, -2.0, 3.0, 0.0, 0.0, np.nan, np.nan, 4.0, -1.0, 2.0, -2.0, 5.0],
            "positive": [0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 0.75, 1.25, 2.5, 5.0, np.nan],
            "unit": [-1.0, -0.75, -0.5, -0.1, 0.0, 0.1, 0.5, 0.75, 1.0, np.nan, 0.25, -0.25],
            "rounding": [-3.141, -2.718, -1.234, -0.126, 0.0, 0.126, 1.234, 2.718, 3.141, 10.019, -10.019, np.nan],
            "integer": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, np.nan],
            "finite": [1.0, -2.5, np.nan, np.inf, -np.inf, 0.0, 3.5, 8.0, -9.0, 1e20, -1e20, np.nan],
            "bool_left": [True, True, False, False, None, True, False, None, True, False, None, None],
            "bool_right": [True, False, True, False, True, None, None, False, None, None, True, None],
            "bool_third": [False, True, True, False, None, False, True, True, None, None, None, None],
            "m1": [1.0, np.nan, 3.0, 0.0, -1.0, 2.0, np.nan, 4.0, 5.0, np.nan, 7.0, np.nan],
            "m2": [10.0, 20.0, np.nan, 0.0, 2.0, -2.0, np.nan, 1.0, np.nan, 6.0, 8.0, np.nan],
            "m3": [100.0, np.nan, 30.0, np.nan, 3.0, 4.0, np.nan, -1.0, 2.0, 9.0, np.nan, np.nan],
            "pow_base": [1.0, 2.0, 3.0, 4.0, 0.5, 5.0, 2.0, 8.0, 9.0, 10.0, 4.0, np.nan],
            "pow_exp": [0.0, 1.0, 2.0, -1.0, 3.0, 0.5, -2.0, 1.0, 0.5, 2.0, -0.5, 2.0],
            "date": pd.to_datetime(
                [
                    "2023-12-31",
                    "2024-01-01",
                    "2024-02-28",
                    "2024-02-29",
                    "2024-03-31",
                    "2024-04-01",
                    "2024-06-30",
                    "2024-07-01",
                    "2024-09-30",
                    "2024-12-31",
                    "2025-01-01",
                    None,
                ]
            ),
        }
    ).assign(
        date2=lambda frame: frame["date"]
        + pd.to_timedelta([1, -2, 2, 1, 10, 0, -5, 30, 1, 2, 365, 1], unit="D")
    )


def _direct_contracts(source: pd.DataFrame) -> dict[str, DirectContract]:
    """显式定义每个 DIRECT 算符的独立计算契约。"""
    left = source["left"]
    right = source["right"]
    numeric = source[["m1", "m2", "m3"]]
    booleans = source[["bool_left", "bool_right", "bool_third"]]
    dates = source["date"]

    eq = [
        None if _missing(lhs) or _missing(rhs) else lhs == rhs
        for lhs, rhs in zip(left, right, strict=True)
    ]
    null_if = [
        np.nan if _missing(lhs) or (not _missing(rhs) and lhs == rhs) else lhs
        for lhs, rhs in zip(left, right, strict=True)
    ]
    where = [
        np.nan if _missing(condition) else (lhs if condition else rhs)
        for condition, lhs, rhs in zip(
            source["bool_left"],
            left,
            right,
            strict=True,
        )
    ]

    date_null = dates.isna().to_numpy()

    def date_values(values: pd.Series) -> list[object]:
        """把 Pandas 日期访问器结果中的 NaT 位置恢复为 NULL。"""
        result = values.astype(object).tolist()
        return [None if missing else value for value, missing in zip(result, date_null, strict=True)]

    contracts = {
        "binary.add": DirectContract(direct("binary.add", {"left": "left", "right": "right"}), _arithmetic(left, right, operator.add)),
        "binary.and": DirectContract(direct("binary.and", {"left": "bool_left", "right": "bool_right"}), _logical(source["bool_left"], source["bool_right"], operator.and_)),
        "binary.days_between": DirectContract(direct("binary.days_between", {"left": "date", "right": "date2"}), (source["date"] - source["date2"]).dt.days),
        "binary.div": DirectContract(direct("binary.div", {"left": "left", "right": "right"}), _arithmetic(left, right, operator.truediv, zero_is_null=True)),
        "binary.eq": DirectContract(direct("binary.eq", {"left": "left", "right": "right"}), eq),
        "binary.floor_div": DirectContract(direct("binary.floor_div", {"left": "left", "right": "right"}), _arithmetic(left, right, lambda lhs, rhs: np.floor(lhs / rhs), zero_is_null=True)),
        "binary.ge": DirectContract(direct("binary.ge", {"left": "left", "right": "right"}), _comparison(left, right, operator.ge)),
        "binary.gt": DirectContract(direct("binary.gt", {"left": "left", "right": "right"}), _comparison(left, right, operator.gt)),
        "binary.le": DirectContract(direct("binary.le", {"left": "left", "right": "right"}), _comparison(left, right, operator.le)),
        "binary.lt": DirectContract(direct("binary.lt", {"left": "left", "right": "right"}), _comparison(left, right, operator.lt)),
        "binary.maximum": DirectContract(direct("binary.maximum", {"left": "left", "right": "right"}), _arithmetic(left, right, max)),
        "binary.minimum": DirectContract(direct("binary.minimum", {"left": "left", "right": "right"}), _arithmetic(left, right, min)),
        "binary.mod": DirectContract(direct("binary.mod", {"left": "left", "right": "right"}), _arithmetic(left, right, operator.mod, zero_is_null=True)),
        "binary.mul": DirectContract(direct("binary.mul", {"left": "left", "right": "right"}), _arithmetic(left, right, operator.mul)),
        "binary.ne": DirectContract(direct("binary.ne", {"left": "left", "right": "right"}), [None if value is None else not value for value in eq]),
        "binary.null_if": DirectContract(direct("binary.null_if", {"left": "left", "right": "right"}), null_if),
        "binary.or": DirectContract(direct("binary.or", {"left": "bool_left", "right": "bool_right"}), _logical(source["bool_left"], source["bool_right"], operator.or_)),
        "binary.pow": DirectContract(direct("binary.pow", {"left": "pow_base", "right": "pow_exp"}), np.power(source["pow_base"], source["pow_exp"])),
        "binary.sub": DirectContract(direct("binary.sub", {"left": "left", "right": "right"}), _arithmetic(left, right, operator.sub)),
        "binary.xor": DirectContract(direct("binary.xor", {"left": "bool_left", "right": "bool_right"}), _logical(source["bool_left"], source["bool_right"], operator.xor)),
        "multiary.add": DirectContract(direct("multiary.add", {"cols": ["m1", "m2", "m3"]}), numeric.sum(axis=1, min_count=1)),
        "multiary.and": DirectContract(direct("multiary.and", {"cols": ["bool_left", "bool_right", "bool_third"]}), _row_boolean(booleans, mode="and")),
        "multiary.coalesce": DirectContract(direct("multiary.coalesce", {"cols": ["m1", "m2", "m3"]}), numeric.bfill(axis=1).iloc[:, 0]),
        "multiary.count": DirectContract(direct("multiary.count", {"cols": ["m1", "m2", "m3"]}), numeric.count(axis=1)),
        "multiary.max": DirectContract(direct("multiary.max", {"cols": ["m1", "m2", "m3"]}), numeric.max(axis=1, skipna=True)),
        "multiary.mean": DirectContract(direct("multiary.mean", {"cols": ["m1", "m2", "m3"]}), numeric.mean(axis=1, skipna=True)),
        "multiary.min": DirectContract(direct("multiary.min", {"cols": ["m1", "m2", "m3"]}), numeric.min(axis=1, skipna=True)),
        "multiary.mul": DirectContract(direct("multiary.mul", {"cols": ["m1", "m2", "m3"]}), numeric.prod(axis=1, min_count=1)),
        "multiary.or": DirectContract(direct("multiary.or", {"cols": ["bool_left", "bool_right", "bool_third"]}), _row_boolean(booleans, mode="or")),
        "multiary.std": DirectContract(direct("multiary.std", {"cols": ["m1", "m2", "m3"]}, {"ddof": 1}), numeric.std(axis=1, ddof=1)),
        "multiary.var": DirectContract(direct("multiary.var", {"cols": ["m1", "m2", "m3"]}, {"ddof": 1}), numeric.var(axis=1, ddof=1)),
        "nullary.false": DirectContract(direct("nullary.false", {}), [False] * len(source)),
        "nullary.literal": DirectContract(direct("nullary.literal", {}, {"value": 2.5, "dtype": "double"}), [2.5] * len(source)),
        "nullary.true": DirectContract(direct("nullary.true", {}), [True] * len(source)),
        "ternary.where": DirectContract(direct("ternary.where", {"condition": "bool_left", "if_true": "left", "if_false": "right"}), where),
        "unary.abs": DirectContract(direct("unary.abs", {"col": "left"}), left.abs()),
        "unary.acos": DirectContract(direct("unary.acos", {"col": "unit"}), np.arccos(source["unit"])),
        "unary.asin": DirectContract(direct("unary.asin", {"col": "unit"}), np.arcsin(source["unit"])),
        "unary.atan": DirectContract(direct("unary.atan", {"col": "left"}), np.arctan(left)),
        "unary.between": DirectContract(direct("unary.between", {"col": "left"}, {"lower": -2.0, "upper": 4.0, "inclusive": "both"}), [False if _missing(value) else -2.0 <= value <= 4.0 for value in left]),
        "unary.cast": DirectContract(direct("unary.cast", {"col": "integer"}, {"dtype": "double"}), source["integer"].astype(float)),
        "unary.ceil": DirectContract(direct("unary.ceil", {"col": "rounding"}), np.ceil(source["rounding"])),
        "unary.clip": DirectContract(direct("unary.clip", {"col": "left"}, {"lower": -2.0, "upper": 4.0}), left.clip(-2.0, 4.0)),
        "unary.cos": DirectContract(direct("unary.cos", {"col": "left"}), np.cos(left)),
        "unary.day": DirectContract(direct("unary.day", {"col": "date"}), date_values(dates.dt.day)),
        "unary.day_of_year": DirectContract(direct("unary.day_of_year", {"col": "date"}), date_values(dates.dt.dayofyear)),
        "unary.exp": DirectContract(direct("unary.exp", {"col": "unit"}), np.exp(source["unit"])),
        "unary.expm1": DirectContract(direct("unary.expm1", {"col": "unit"}), np.expm1(source["unit"])),
        "unary.floor": DirectContract(direct("unary.floor", {"col": "rounding"}), np.floor(source["rounding"])),
        "unary.get": DirectContract(direct("unary.get", {"col": "left"}), left),
        "unary.is_finite": DirectContract(direct("unary.is_finite", {"col": "finite"}), np.isfinite(source["finite"])),
        "unary.is_month_end": DirectContract(direct("unary.is_month_end", {"col": "date"}), [None if missing else bool(value) for value, missing in zip(dates.dt.is_month_end, date_null, strict=True)]),
        "unary.is_null": DirectContract(direct("unary.is_null", {"col": "left"}), left.isna()),
        "unary.is_quarter_end": DirectContract(direct("unary.is_quarter_end", {"col": "date"}), [None if missing else bool(value) for value, missing in zip(dates.dt.is_quarter_end, date_null, strict=True)]),
        "unary.is_weekend": DirectContract(direct("unary.is_weekend", {"col": "date"}), [None if missing else value >= 5 for value, missing in zip(dates.dt.weekday, date_null, strict=True)]),
        "unary.is_year_end": DirectContract(direct("unary.is_year_end", {"col": "date"}), [None if missing else bool(value) for value, missing in zip(dates.dt.is_year_end, date_null, strict=True)]),
        "unary.isin": DirectContract(direct("unary.isin", {"col": "left"}, {"values": [2.0, 4.0, None]}), [(_missing(value) or value in {2.0, 4.0}) for value in left]),
        "unary.log": DirectContract(direct("unary.log", {"col": "positive"}), np.log(source["positive"])),
        "unary.log10": DirectContract(direct("unary.log10", {"col": "positive"}), np.log10(source["positive"])),
        "unary.log1p": DirectContract(direct("unary.log1p", {"col": "positive"}), np.log1p(source["positive"])),
        "unary.log2": DirectContract(direct("unary.log2", {"col": "positive"}), np.log2(source["positive"])),
        "unary.month": DirectContract(direct("unary.month", {"col": "date"}), date_values(dates.dt.month)),
        "unary.neg": DirectContract(direct("unary.neg", {"col": "left"}), -left),
        "unary.not": DirectContract(direct("unary.not", {"col": "bool_left"}), [None if _missing(value) else not value for value in source["bool_left"]]),
        "unary.not_null": DirectContract(direct("unary.not_null", {"col": "left"}), left.notna()),
        "unary.quarter": DirectContract(direct("unary.quarter", {"col": "date"}), date_values(dates.dt.quarter)),
        "unary.replace": DirectContract(direct("unary.replace", {"col": "integer"}, {"old": [1, 2, 8], "new": [2, 3, -8]}), source["integer"].replace({1: 3, 2: 3, 8: -8})),
        "unary.round": DirectContract(direct("unary.round", {"col": "rounding"}, {"precision": 2}), source["rounding"].round(2)),
        "unary.sign": DirectContract(direct("unary.sign", {"col": "left"}), np.sign(left)),
        "unary.sin": DirectContract(direct("unary.sin", {"col": "left"}), np.sin(left)),
        "unary.sqrt": DirectContract(direct("unary.sqrt", {"col": "positive"}), np.sqrt(source["positive"])),
        "unary.tan": DirectContract(direct("unary.tan", {"col": "unit"}), np.tan(source["unit"])),
        "unary.week": DirectContract(direct("unary.week", {"col": "date"}), date_values(dates.dt.isocalendar().week)),
        "unary.weekday": DirectContract(direct("unary.weekday", {"col": "date"}), date_values(dates.dt.weekday)),
        "unary.year": DirectContract(direct("unary.year", {"col": "date"}), date_values(dates.dt.year)),
    }
    return contracts


def test_direct_contract_inventory_is_exhaustive(direct_source: pd.DataFrame) -> None:
    """显式 oracle 清单必须与注册的 DIRECT 算符集合完全相等。"""
    registered = {
        operation
        for operation, model in Derivative.operators.items()
        if issubclass(model, DirectOperator)
    }
    assert set(_direct_contracts(direct_source)) == registered
    assert len(registered) == 75


@pytest.mark.parametrize(
    "operation",
    sorted(
        operation
        for operation, model in Derivative.operators.items()
        if issubclass(model, DirectOperator)
    ),
)
def test_direct_operator_matches_independent_reference(
    ddb_session,
    direct_source: pd.DataFrame,
    operation: str,
) -> None:
    """每个 DIRECT 算符都通过完整 JSON DSL 与十二行独立参考结果比较。"""
    contract = _direct_contracts(direct_source)[operation]
    result = compute_factors(
        ddb_session,
        direct_source,
        {"actual": contract.definition},
    )
    assert_vector_equal(result["actual"], contract.expected, atol=1e-8, rtol=1e-8)


@pytest.mark.parametrize("inclusive", ["both", "left", "right", "neither"])
def test_between_all_boundary_modes(ddb_session, inclusive: str) -> None:
    """between 的四种开闭区间必须正确处理端点、区间外值和 NULL。"""
    source = pd.DataFrame({"value": [0.0, 1.999, 2.0, 2.001, 3.0, 3.999, 4.0, 4.001, 8.0, np.nan]})
    include_left = inclusive in {"both", "left"}
    include_right = inclusive in {"both", "right"}
    expected = []
    for value in source["value"]:
        if _missing(value):
            expected.append(False)
            continue
        left_ok = value >= 2.0 if include_left else value > 2.0
        right_ok = value <= 4.0 if include_right else value < 4.0
        expected.append(left_ok and right_ok)
    definition = direct(
        "unary.between",
        {"col": "value"},
        {"lower": 2.0, "upper": 4.0, "inclusive": inclusive},
    )
    result = compute_factors(ddb_session, source, {"actual": definition})
    assert_vector_equal(result["actual"], expected)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"lower": -1.0}, [-1.0, -1.0, 0.0, 1.0, 2.0, 5.0, np.nan, 8.0, -1.0, 3.0]),
        ({"upper": 2.0}, [-5.0, -2.0, 0.0, 1.0, 2.0, 2.0, np.nan, 2.0, -3.0, 2.0]),
        ({"lower": -1.0, "upper": 2.0}, [-1.0, -1.0, 0.0, 1.0, 2.0, 2.0, np.nan, 2.0, -1.0, 2.0]),
    ],
)
def test_clip_one_and_two_sided_bounds(
    ddb_session,
    params: dict[str, float],
    expected: list[float],
) -> None:
    """clip 分别覆盖仅下界、仅上界和双边截断。"""
    source = pd.DataFrame({"value": [-5.0, -2.0, 0.0, 1.0, 2.0, 5.0, np.nan, 8.0, -3.0, 3.0]})
    result = compute_factors(
        ddb_session,
        source,
        {"actual": direct("unary.clip", {"col": "value"}, params)},
    )
    assert_vector_equal(result["actual"], expected)


@pytest.mark.parametrize("operation", ["multiary.std", "multiary.var"])
@pytest.mark.parametrize("ddof", [0, 1])
def test_multiary_dispersion_both_ddof_branches(
    ddb_session,
    operation: str,
    ddof: int,
) -> None:
    """逐行方差和标准差必须区分总体与样本自由度。"""
    source = pd.DataFrame(
        {
            "a": [1.0, 1.0, np.nan, 1.0, 2.0, np.nan, 5.0, 8.0, 2.0, np.nan],
            "b": [2.0, np.nan, np.nan, 3.0, 4.0, 2.0, 5.0, 4.0, np.nan, np.nan],
            "c": [3.0, np.nan, np.nan, 5.0, 8.0, 4.0, 5.0, 0.0, 6.0, np.nan],
        }
    )
    expected = (
        source.std(axis=1, ddof=ddof)
        if operation.endswith("std")
        else source.var(axis=1, ddof=ddof)
    )
    result = compute_factors(
        ddb_session,
        source,
        {
            "actual": direct(
                operation,
                {"cols": ["a", "b", "c"]},
                {"ddof": ddof},
            )
        },
    )
    assert_vector_equal(result["actual"], expected)


def test_multiary_dispersion_is_stable_for_tiny_and_large_differences(
    ddb_session,
) -> None:
    """先中心化的方差算法不能把极小值或大数近邻错误消成零。"""
    epsilon = float(np.float32(2**-23))
    source = pd.DataFrame(
        {
            "a": [0.0, 1_000_000_000_000.0, np.nan],
            "b": [0.0, 1_000_000_000_001.0, np.nan],
            "c": [epsilon, 1_000_000_000_002.0, np.nan],
        }
    )
    definitions = {
        "std0": direct(
            "multiary.std",
            {"cols": ["a", "b", "c"]},
            {"ddof": 0},
        ),
        "std1": direct(
            "multiary.std",
            {"cols": ["a", "b", "c"]},
            {"ddof": 1},
        ),
        "var0": direct(
            "multiary.var",
            {"cols": ["a", "b", "c"]},
            {"ddof": 0},
        ),
        "constant_std": direct(
            "multiary.std",
            {"cols": [1.0, 2.0, 3.0]},
            {"ddof": 0},
        ),
    }
    result = compute_factors(ddb_session, source, definitions)
    assert_vector_equal(result["std0"], source.std(axis=1, ddof=0), atol=1e-12)
    assert_vector_equal(result["std1"], source.std(axis=1, ddof=1), atol=1e-12)
    assert_vector_equal(result["var0"], source.var(axis=1, ddof=0), atol=1e-20)
    assert_vector_equal(
        result["constant_std"],
        [np.std([1.0, 2.0, 3.0])] * len(source),
        atol=1e-12,
    )


@pytest.mark.parametrize(
    ("value", "dtype", "expected"),
    [
        (True, "bool", [True] * 10),
        (7, "int", [7] * 10),
        (3.5, "double", [3.5] * 10),
        ("bank", "string", ["bank"] * 10),
        ("bank", "symbol", ["bank"] * 10),
        ("2024-02-29", "date", [pd.Timestamp("2024-02-29")] * 10),
        (
            "2024-02-29T09:30:00.123",
            "timestamp",
            [pd.Timestamp("2024-02-29 09:30:00.123")] * 10,
        ),
        (None, "double", [np.nan] * 10),
    ],
)
def test_literal_types_broadcast_through_complete_runtime(
    ddb_session,
    value: object,
    dtype: str,
    expected: list[object],
) -> None:
    """各类字面量含 typed NULL 和 SYMBOL 都必须广播到完整表长度。"""
    source = pd.DataFrame({"row": range(10)})
    definition = direct("nullary.literal", {}, {"value": value, "dtype": dtype})
    result = compute_factors(ddb_session, source, {"actual": definition})
    assert_vector_equal(result["actual"], expected)
