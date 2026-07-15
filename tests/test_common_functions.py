"""验证算符复用的 DolphinDB 公共函数。"""

import pytest

from core.dolphindb.common import (
    BROADCAST_LIKE,
    CAST_VALUE,
    CROSS_SECTION_RANK,
    CROSS_SECTION_SLOPE,
    DIVIDE_OR_NULL,
    IS_DICTIONARY_FORM,
    IS_FINITE_NUMBER,
    IS_SCALAR_FORM,
    IS_TABLE_FORM,
    IS_VECTOR_FORM,
    MASK_EXPANDING_RESULT,
    MASK_PAIR_EXPANDING_RESULT,
    ROLLING_INTERCEPT,
    ROLLING_MIN_PERIODS,
    ROLLING_SLOPE,
    ROLLING_TRUE_COUNT,
)
from core.dolphindb.function import DolphinDBFunction

from .ddb_cases import DDBCase, assert_ddb_cases


COMMON_FUNCTIONS = (
    BROADCAST_LIKE,
    CAST_VALUE,
    CROSS_SECTION_RANK,
    CROSS_SECTION_SLOPE,
    DIVIDE_OR_NULL,
    IS_DICTIONARY_FORM,
    IS_FINITE_NUMBER,
    IS_SCALAR_FORM,
    IS_TABLE_FORM,
    IS_VECTOR_FORM,
    MASK_EXPANDING_RESULT,
    MASK_PAIR_EXPANDING_RESULT,
    ROLLING_INTERCEPT,
    ROLLING_MIN_PERIODS,
    ROLLING_SLOPE,
    ROLLING_TRUE_COUNT,
)


FORM_CASES = {
    "is_scalar_form": (
        ("1", True),
        ("true", True),
        ('"text"', True),
        ("`A", True),
        ("2024.01.01", True),
        ("1 2", False),
        ("true false", False),
        ("`A`B", False),
        ("dict(STRING, ANY)", False),
        ("table(1 as value)", False),
    ),
    "is_vector_form": (
        ("1 2", True),
        ("double(1..3)", True),
        ("true false", True),
        ("`A`B", True),
        ("2024.01.01 2024.01.02", True),
        ("1", False),
        ("false", False),
        ('"text"', False),
        ("dict(STRING, ANY)", False),
        ("table(1 as value)", False),
    ),
    "is_dictionary_form": (
        ("dict(STRING, ANY)", True),
        ("dict(INT, DOUBLE)", True),
        ("dict(SYMBOL, STRING)", True),
        ("dict(DATE, DOUBLE)", True),
        ("dict(LONG, BOOL)", True),
        ("1", False),
        ("true", False),
        ("1 2", False),
        ("`A`B", False),
        ("table(1 as value)", False),
    ),
    "is_table_form": (
        ("table(1 as value)", True),
        ("table(1 2 as value)", True),
        ("table(1 as x, 2 as y)", True),
        ("table(2024.01.01 as time, `A as code)", True),
        ("table(true false as value)", True),
        ("1", False),
        ("false", False),
        ("1 2", False),
        ("`A`B", False),
        ("dict(STRING, ANY)", False),
    ),
}


def _common_cases(function: DolphinDBFunction) -> list[DDBCase]:
    """为指定公共函数构造十个输入输出场景。"""
    name = function.name
    if name in FORM_CASES:
        return [
            DDBCase(f"{name}({value})", str(expected).lower())
            for value, expected in FORM_CASES[name]
        ]
    if name == "broadcast_like":
        return [
            DDBCase(
                f"{name}(value, reference)",
                "take(value,size(reference))",
                f"value={seed + 0.5}; reference=0..{seed + 2}",
            )
            for seed in range(10)
        ]
    if name == "cast_value":
        values = [
            ("true", "bool", "bool(true)"),
            ("1.8", "int", "int(1.8)"),
            ("2", "long", "long(2)"),
            ("1.25", "float", "float(1.25)"),
            ("1.25", "double", "double(1.25)"),
            ("123", "string", "string(123)"),
            ('"abc"', "symbol", "`abc"),
            ('"2024-02-03"', "date", 'temporalParse("2024-02-03","yyyy-MM-dd")'),
            ('"2024-02-03T04:05:06"', "timestamp", 'timestamp(temporalParse("2024-02-03T04:05:06","yyyy-MM-ddTHH:mm:ss"))'),
            ('"2024-02-03T04:05:06.123"', "timestamp", 'timestamp(temporalParse("2024-02-03T04:05:06.123","yyyy-MM-ddTHH:mm:ss.SSS"))'),
        ]
        return [
            DDBCase(f'{name}({value},"{dtype}")', expected)
            for value, dtype, expected in values
        ]
    if name == "cross_section_rank":
        ties = ["min", "max", "average", "first", "dense"]
        cases = []
        for seed in range(10):
            tie = ties[seed % 5]
            ascending = seed % 2 == 0
            percent = seed % 3 == 0
            if tie == "dense":
                expected = f"denseRank(value,{str(ascending).lower()},true,{str(percent).lower()})"
            else:
                expected = f"rank(value,{str(ascending).lower()},,true,`{tie},{str(percent).lower()})"
            if not percent:
                expected = f"({expected})+1"
            cases.append(
                DDBCase(
                    f'{name}(value,{str(ascending).lower()},"{tie}",{str(percent).lower()})',
                    expected,
                    f"value=double([3,1,2,2,5,4,4,6])+{seed}",
                )
            )
        return cases
    if name == "cross_section_slope":
        return [
            DDBCase(
                f"{name}(left,right)",
                "covar(left,right)/covar(left,left)",
                f"left=double(1..{10 + seed}); right={seed + 1}.0+{1.5 + seed / 10}*left+sin(left)",
            )
            for seed in range(10)
        ]
    if name == "divide_or_null":
        return [
            DDBCase(
                f"{name}(left,right)",
                "iif(isNull(right)||right==0,NULL,left/right)",
                f"left=double(-4..5)+{seed}; right=double(-5..4)",
            )
            for seed in range(10)
        ]
    if name == "is_finite_number":
        return [
            DDBCase(
                f"{name}(value)",
                "isValid(value)&&!isNanInf(value,true)",
                f"value=double(1..10); value[{seed}]=NULL",
            )
            for seed in range(10)
        ]
    if name == "mask_expanding_result":
        return [
            DDBCase(
                f"{name}(result,value,minimum)",
                "iif(cumcount(value)<minimum,NULL,result)",
                f"value=double(1..{12 + seed}); value[{seed % 5}]=NULL; result=cumsum(value); minimum={1 + seed % 5}",
            )
            for seed in range(10)
        ]
    if name == "mask_pair_expanding_result":
        return [
            DDBCase(
                f"{name}(result,left,right,minimum)",
                "iif(cumcount(iif(isValid(left)&&isValid(right),1,int(NULL)))<minimum,NULL,result)",
                f"left=double(1..{12 + seed}); right=2*left; left[{seed % 5}]=NULL; right[{(seed + 2) % 7}]=NULL; result=cumcovar(left,right); minimum={1 + seed % 5}",
            )
            for seed in range(10)
        ]
    if name == "rolling_min_periods":
        return [
            DDBCase(
                f"{name}(window,minimum)",
                "iif(isNull(minimum),window,minimum)",
                f"window={seed + 1}; minimum={'int(NULL)' if seed % 2 == 0 else str(1 + seed // 2)}",
            )
            for seed in range(10)
        ]
    if name in {"rolling_slope", "rolling_intercept"}:
        cases = []
        for seed in range(10):
            window = 3 + seed % 5
            minimum = 1 + seed % window
            slope = "mbeta(right,left,window,minimum)"
            expected = slope if name == "rolling_slope" else f"mavg(right,window,minimum)-({slope})*mavg(left,window,minimum)"
            cases.append(
                DDBCase(
                    f"{name}(left,right,window,minimum)",
                    expected,
                    f"left=double(1..{20 + seed})+sin(double(1..{20 + seed})); right=2.5*left+cos(left); window={window}; minimum={minimum}",
                )
            )
        return cases
    if name == "rolling_true_count":
        return [
            DDBCase(
                f"{name}(value,window,minimum)",
                "msum(int(nullFill(value,false)),window,minimum)",
                f"value=((0..{19 + seed}+{seed})%3)==0; window={3 + seed % 5}; minimum={1 + seed % (3 + seed % 5)}",
            )
            for seed in range(10)
        ]
    raise AssertionError(f"缺少公共函数用例：{name}")


@pytest.mark.parametrize("function", COMMON_FUNCTIONS, ids=lambda function: function.name)
def test_common_function(ddb_session, function: DolphinDBFunction) -> None:
    """每个算符公共函数均执行十个输入输出场景。"""
    assert_ddb_cases(ddb_session, function.name, _common_cases(function))
