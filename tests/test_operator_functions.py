"""逐个验证每个算符定义的 DolphinDB 纯函数。"""

from typing import Type, get_args

import pytest

from core.operators import Derivative
from core.operators.base import (
    CrossSectionOperator,
    DirectOperator,
    OperatorBase,
    TimeSeriesOperator,
)

from .ddb_cases import DDBCase, assert_ddb_cases


def _operation(model: Type[OperatorBase]) -> str:
    """读取算符模型声明的 op 字面量。"""
    return get_args(model.model_fields["op"].annotation)[0]


def _numeric(seed: int, *, positive: bool = False, unit: bool = False) -> str:
    """生成满足指定数值范围的 DolphinDB 向量表达式。"""
    if unit:
        return f"sin(double(0..8) + {seed})"
    if positive:
        return f"double(1..9) + {seed}"
    return f"double(-4..4) + {seed / 10}"


def _direct_cases(model: Type[OperatorBase]) -> list[DDBCase]:
    """为一个 DIRECT 算符构造十个纯函数场景。"""
    operation = _operation(model)
    function = model.function.name
    name = operation.split(".", 1)[1]
    simple_unary = {
        "abs": "abs(col)",
        "acos": "acos(col)",
        "asin": "asin(col)",
        "atan": "atan(col)",
        "ceil": "ceil(col)",
        "cos": "cos(col)",
        "exp": "exp(col)",
        "expm1": "expm1(col)",
        "floor": "floor(col)",
        "get": "col",
        "log": "log(col)",
        "log10": "log10(col)",
        "log1p": "log1p(col)",
        "log2": "log2(col)",
        "neg": "-col",
        "sign": "signum(col)",
        "sin": "sin(col)",
        "sqrt": "sqrt(col)",
        "tan": "tan(col)",
    }
    date_unary = {
        "day": "dayOfMonth(col)",
        "day_of_year": "dayOfYear(col)",
        "is_month_end": "isMonthEnd(col)",
        "is_quarter_end": "isQuarterEnd(col)",
        "is_weekend": "weekday(col, false) >= 5",
        "is_year_end": "isYearEnd(col)",
        "month": "monthOfYear(col)",
        "quarter": "quarterOfYear(col)",
        "week": "weekOfYear(col)",
        "weekday": "weekday(col, false)",
        "year": "year(col)",
    }
    simple_binary = {
        "add": "left + right",
        "eq": "left == right",
        "ge": "left >= right",
        "gt": "left > right",
        "le": "left <= right",
        "lt": "left < right",
        "mul": "left * right",
        "ne": "left != right",
        "pow": "pow(left, right)",
        "sub": "left - right",
    }

    if operation in {"nullary.true", "nullary.false"}:
        expected = "true" if name == "true" else "false"
        return [DDBCase(f"{function}()", expected) for _ in range(10)]
    if operation == "nullary.literal":
        values = [
            ("true", '"bool"', "bool(true)"),
            ("7", '"int"', "int(7)"),
            ("7", '"long"', "long(7)"),
            ("1.25", '"float"', "float(1.25)"),
            ("1.25", '"double"', "double(1.25)"),
            ('"abc"', '"string"', 'string("abc")'),
            ('"abc"', '"symbol"', '`abc'),
            ('"2024-01-02"', '"date"', 'temporalParse("2024-01-02","yyyy-MM-dd")'),
            ('"2024-01-02T03:04:05"', '"timestamp"', 'timestamp(temporalParse("2024-01-02T03:04:05","yyyy-MM-ddTHH:mm:ss"))'),
            ("NULL", '"date"', "date(NULL)"),
            ("NULL", '"timestamp"', "timestamp(NULL)"),
            ("3.5", "string(NULL)", "3.5"),
        ]
        return [DDBCase(f"{function}({value}, {dtype})", expected) for value, dtype, expected in values]
    if operation.startswith("unary.") and name in simple_unary:
        cases = []
        for seed in range(10):
            unit = name in {"acos", "asin"}
            positive = name in {"log", "log10", "log1p", "log2", "sqrt"}
            col = _numeric(seed, positive=positive, unit=unit)
            cases.append(
                DDBCase(
                    f"{function}(col)",
                    simple_unary[name],
                    f"col={col}",
                )
            )
        return cases
    if operation.startswith("unary.") and name in date_unary:
        return [
            DDBCase(
                f"{function}(col)",
                date_unary[name],
                f"col=2020.01.01 + (0..9) * {seed + 1}",
            )
            for seed in range(10)
        ]
    if operation == "unary.not":
        return [
            DDBCase(f"{function}(col)", "!col", f"col=((0..9 + {seed}) % 3) == 0")
            for seed in range(10)
        ]
    if operation in {"unary.is_null", "unary.not_null", "unary.is_finite"}:
        expected = {
            "unary.is_null": "isNull(col)",
            "unary.not_null": "!isNull(col)",
            "unary.is_finite": "isValid(col) && !isNanInf(col, true)",
        }[operation]
        return [
            DDBCase(
                f"{function}(col)",
                expected,
                f"col=double(1..10); col[{seed}]=NULL",
            )
            for seed in range(10)
        ]
    if operation == "unary.cast":
        dtypes = ["bool", "int", "long", "float", "double", "string", "symbol", "date", "timestamp", "double"]
        values = ["1", "1.8", "2", "1.25", "1.25", "123", "123", "2024.01.02", "2024.01.02T03:04:05", "-2"]
        cases = []
        for dtype, value in zip(dtypes, values, strict=True):
            expected = (
                f"symbol(enlist(string({value})))[0]"
                if dtype == "symbol"
                else f"{dtype}({value})"
            )
            cases.append(DDBCase(f'{function}({value}, "{dtype}")', expected))
        return cases
    if operation == "unary.replace":
        return [
            DDBCase(
                f"{function}(col, old, new)",
                "replace(replace(col, old[0], new[0]), old[1], new[1])",
                f"col=(0..9)+{seed}; old={seed} {seed + 3}; new={seed + 20} {seed + 30}",
            )
            for seed in range(10)
        ]
    if operation == "unary.round":
        return [
            DDBCase(
                f"{function}(col, {seed % 4})",
                f"round(col, {seed % 4})",
                f"col=double(-4..4)/{seed + 2}",
            )
            for seed in range(10)
        ]
    if operation == "unary.clip":
        return [
            DDBCase(
                f"{function}(col, lower, upper)",
                "iif(col < lower, lower, iif(col > upper, upper, col))",
                f"col=double(-5..5)+{seed / 10}; lower={-2 + seed / 20}; upper={2 + seed / 20}",
            )
            for seed in range(10)
        ]
    if operation == "unary.isin":
        return [
            DDBCase(
                f"{function}(col, values)",
                "col in values",
                f"col=(0..9)+{seed}; values={seed} {seed + 2} {seed + 7}",
            )
            for seed in range(10)
        ]
    if operation == "unary.between":
        inclusives = ["both", "left", "right", "neither"]
        cases = []
        for seed in range(10):
            inclusive = inclusives[seed % 4]
            left = ">=" if inclusive in {"both", "left"} else ">"
            right = "<=" if inclusive in {"both", "right"} else "<"
            cases.append(
                DDBCase(
                    f'{function}(col, lower, upper, "{inclusive}")',
                    f"(col {left} lower) && (col {right} upper)",
                    f"col=double(-4..4)+{seed / 10}; lower=-2.0; upper=2.0",
                )
            )
        return cases
    if operation.startswith("binary.") and name in simple_binary:
        return [
            DDBCase(
                f"{function}(left, right)",
                simple_binary[name],
                f"left=double(1..9)+{seed}; right=double(9..1)+{seed / 10}",
            )
            for seed in range(10)
        ]
    if operation in {"binary.and", "binary.or", "binary.xor"}:
        expression = {"binary.and": "left && right", "binary.or": "left || right", "binary.xor": "xor(left, right)"}[operation]
        return [
            DDBCase(
                f"{function}(left, right)",
                expression,
                f"left=((0..9+{seed})%2)==0; right=((0..9+{seed})%3)==0",
            )
            for seed in range(10)
        ]
    if operation in {"binary.div", "binary.floor_div", "binary.mod"}:
        quotient = "iif(right == 0, NULL, left / right)"
        expected = {
            "binary.div": quotient,
            "binary.floor_div": f"floor({quotient})",
            "binary.mod": f"left - floor({quotient}) * right",
        }[operation]
        return [
            DDBCase(
                f"{function}(left, right)",
                expected,
                f"left=double(-4..5)+{seed}; right=double(-5..4)",
            )
            for seed in range(10)
        ]
    if operation in {"binary.minimum", "binary.maximum"}:
        comparison = "<=" if name == "minimum" else ">="
        return [
            DDBCase(
                f"{function}(left, right)",
                f"iif(isNull(left) || isNull(right), NULL, iif(left {comparison} right, left, right))",
                f"left=double(1..10); right=double(10..1); left[{seed}]=NULL",
            )
            for seed in range(10)
        ]
    if operation == "binary.null_if":
        return [
            DDBCase(
                f"{function}(left, right)",
                "iif(left == right, NULL, left)",
                f"left=(0..9)+{seed}; right=iif((0..9)%3==0, left, left+1)",
            )
            for seed in range(10)
        ]
    if operation == "binary.days_between":
        return [
            DDBCase(
                f"{function}(left, right)",
                'temporalDiff(date(left), date(right), "d")',
                f"left=2024.01.01+0..9; right=left+{seed + 1}",
            )
            for seed in range(10)
        ]
    if operation == "ternary.where":
        return [
            DDBCase(
                f"{function}(condition, if_true, if_false)",
                "iif(condition, if_true, if_false)",
                f"condition=((0..9+{seed})%3)==0; if_true=0..9; if_false=10..19",
            )
            for seed in range(10)
        ]
    if operation.startswith("multiary."):
        reducer = {
            "multiary.add": "rowSum",
            "multiary.and": "rowAnd",
            "multiary.count": "rowCount",
            "multiary.max": "rowMax",
            "multiary.mean": "rowAvg",
            "multiary.min": "rowMin",
            "multiary.mul": "rowProd",
            "multiary.or": "rowOr",
        }.get(operation)
        cases = []
        for seed in range(10):
            if operation in {"multiary.and", "multiary.or"}:
                setup = (
                    f"cols=array(ANY,0); cols.append!(((0..9+{seed})%2)==0); "
                    f"cols.append!(((0..9+{seed})%3)==0); cols.append!(((0..9+{seed})%5)==0)"
                )
            elif operation == "multiary.coalesce":
                setup = (
                    "a=double(1..10); b=double(11..20); a[0 3 6]=NULL; b[3 7]=NULL; "
                    f"c=take(double({seed}),10); cols=array(ANY,0); cols.append!(a); cols.append!(b); cols.append!(c)"
                )
            else:
                setup = (
                    f"cols=array(ANY,0); cols.append!(double(1..10)+{seed}); "
                    f"cols.append!(double(10..1)-{seed}); cols.append!(take(double({seed + 2}),10))"
                )
            if operation == "multiary.coalesce":
                expected = "nullFill(a, nullFill(b, c))"
                actual = f"{function}(cols)"
            elif operation == "multiary.std":
                ddof = seed % 2
                expected = f"unifiedCall({'rowStd' if ddof else 'rowStdp'}, cols)"
                actual = f"{function}(cols, {ddof})"
            elif operation == "multiary.var":
                ddof = seed % 2
                expected = f"unifiedCall({'rowVar' if ddof else 'rowVarp'}, cols)"
                actual = f"{function}(cols, {ddof})"
            else:
                expected = f"unifiedCall({reducer}, cols)"
                actual = f"{function}(cols)"
            cases.append(DDBCase(actual, expected, setup))
        return cases
    raise AssertionError(f"缺少 DIRECT 用例：{operation}")


def _series_setup(seed: int, *, boolean: bool = False) -> str:
    """生成时序算符测试共用的输入向量脚本。"""
    if boolean:
        return f"col=((0..{19 + seed}+{seed})%4)<2"
    return (
        f"n={20 + seed}; col=double(1..n)+sin(double(1..n)*0.37+{seed}); "
        "left=col; right=2.5*col+cos(double(1..n)*0.23)"
    )


def _ewm_cases(model: Type[OperatorBase]) -> list[DDBCase]:
    """为一个指数加权算符构造十个场景。"""
    operation = _operation(model)
    function = model.function.name
    name = operation.split(".", 1)[1]
    builtin_name = {"ewm_mean": "ewmMean", "ewm_std": "ewmStd", "ewm_var": "ewmVar", "ewm_cov": "ewmCov", "ewm_corr": "ewmCorr"}[name]
    binary = operation.startswith("binary.")
    cases = []
    for seed in range(10):
        choice = seed % 4
        decay = ["double(NULL)"] * 4
        decay[choice] = [f"double({seed + 1})", f"double({seed + 2})", f"double({seed + 1})", f"double({0.2 + seed / 100})"][choice]
        minimum = seed % 4
        adjust = "true" if seed % 2 == 0 else "false"
        ignore = "true" if seed % 3 == 0 else "false"
        bias = "true" if seed % 2 else "false"
        operands = ["left", "right"] if binary else ["col"]
        arguments = [*operands, *decay, str(minimum), adjust, ignore]
        if name != "ewm_mean":
            arguments.append(bias)
        actual = f"{function}({', '.join(arguments)})"
        placeholders = ["", "", "", ""]
        placeholders[choice] = decay[choice]
        first = "left" if binary else "col"
        expected_arguments = [first, *placeholders, str(minimum), adjust, ignore]
        if binary:
            expected_arguments.extend(["right", bias])
        elif name != "ewm_mean":
            expected_arguments.append(bias)
        expected = f"{builtin_name}({', '.join(expected_arguments)})"
        cases.append(DDBCase(actual, expected, _series_setup(seed)))
    return cases


def _talib_cases(model: Type[OperatorBase]) -> list[DDBCase]:
    """为一个 TA-Lib 算符构造十个场景。"""
    operation = _operation(model)
    function = model.function.name
    name = operation.split(".", 1)[1]
    cases = []
    for seed in range(10):
        setup = (
            f"n={80 + seed}; base=double(1..n)+sin(double(1..n)*0.11+{seed}); "
            "open=base+0.1; high=base+1.2; low=base-1.1; "
            "close=base+cos(double(1..n)*0.07); volume=long(1000+3*(1..n)); col=close"
        )
        values: dict[str, str] = {
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "col": "col",
            "time_period": str(5 + seed % 5),
            "fast_period": str(3 + seed % 2),
            "slow_period": str(8 + seed % 3),
            "signal_period": str(3 + seed % 3),
            "ma_type": str(seed % 3),
            "nbdev": str(1.0 + seed / 10),
            "vfactor": str(0.5 + seed / 25),
            "period1": "3",
            "period2": "6",
            "period3": "12",
        }
        if operation == "talib.macd":
            values["output"] = f'"{["macd", "signal", "hist"][seed % 3]}"'
        elif operation == "talib.bBands":
            values["nbdev_up"] = str(1.5 + seed / 20)
            values["nbdev_down"] = str(1.2 + seed / 20)
            values["output"] = f'"{["upper", "middle", "lower"][seed % 3]}"'
        elif operation == "talib.aroon":
            values["output"] = f'"{["down", "up"][seed % 2]}"'

        arguments = [values[name] for name in model.function.parameters]
        actual = f"{function}({', '.join(arguments)})"
        raw_arguments = []
        for parameter in model.function.parameters:
            if parameter == "output":
                continue
            value = values[parameter]
            raw_arguments.append(f"int({value})" if "period" in parameter or parameter == "ma_type" else value)
        if operation in {"talib.macd", "talib.bBands", "talib.aroon"}:
            selected_output = values["output"].strip('"')
            if operation == "talib.macd":
                index = {"macd": 0, "signal": 1, "hist": 2}[selected_output]
            elif operation == "talib.bBands":
                index = {"upper": 0, "middle": 1, "lower": 2}[selected_output]
            else:
                index = {"down": 0, "up": 1}[selected_output]
            expected = f"ta::{name}({', '.join(raw_arguments)})[{index}]"
        else:
            expected = f"ta::{name}({', '.join(raw_arguments)})"
        cases.append(DDBCase(actual, expected, setup))
    return cases


def _time_series_cases(model: Type[OperatorBase]) -> list[DDBCase]:
    """为一个 TS 算符构造十个纯函数场景。"""
    operation = _operation(model)
    function = model.function.name
    name = operation.split(".", 1)[1]
    if operation.startswith("talib."):
        return _talib_cases(model)
    if "ewm_" in operation:
        return _ewm_cases(model)
    if operation in {"unary.shift", "unary.diff", "unary.pct_change", "unary.log_return"}:
        cases = []
        for seed in range(10):
            periods = 1 + seed % 4
            expected = {
                "unary.shift": f"move(col, {periods})",
                "unary.diff": f"deltas(col, {periods})",
                "unary.pct_change": f"iif(isNull(move(col,{periods}))||move(col,{periods})==0,NULL,col/move(col,{periods}))-1",
                "unary.log_return": f"deltas(log(col), {periods})",
            }[operation]
            cases.append(DDBCase(f"{function}(col, {periods})", expected, _series_setup(seed)))
        return cases
    if operation == "unary.changed":
        cases = []
        for seed in range(10):
            null_equal = seed % 2 == 0
            values = [seed, seed, seed + 1, None, None, seed + 1, seed + 2, seed + 2, None, seed]
            expected = [True]
            for current, previous in zip(values[1:], values[:-1], strict=True):
                if current is None and previous is None:
                    expected.append(not null_equal)
                elif current is None or previous is None:
                    expected.append(True)
                else:
                    expected.append(current != previous)
            value_text = ",".join("NULL" if value is None else str(value) for value in values)
            expected_text = " ".join("true" if value else "false" for value in expected)
            cases.append(
                DDBCase(
                    f"{function}(col, {'true' if null_equal else 'false'})",
                    expected_text,
                    f"col=double([{value_text}])",
                )
            )
        return cases
    if operation in {"unary.ffill", "unary.bfill"}:
        fill = name
        return [
            DDBCase(
                f"{function}(col, {('int(NULL)' if seed % 2 == 0 else str(1 + seed % 3))})",
                f"{fill}(col{'' if seed % 2 == 0 else ', ' + str(1 + seed % 3)})",
                f"col=double(1..10); col[{seed % 5} {5 + seed % 5}]=NULL",
            )
            for seed in range(10)
        ]
    if operation == "unary.consecutive_count":
        return [
            DDBCase(f"{function}(col)", "cumPositiveStreak(col)", _series_setup(seed, boolean=True))
            for seed in range(10)
        ]
    if operation == "unary.bars_since":
        cases = []
        for seed in range(10):
            flags = [((index + seed) % (3 + seed % 3) == 0) for index in range(12)]
            expected: list[int | None] = []
            last: int | None = None
            for index, flag in enumerate(flags):
                if flag:
                    last = index
                expected.append(None if last is None else index - last)
            flags_text = " ".join("true" if flag else "false" for flag in flags)
            expected_text = "int([" + ",".join("NULL" if value is None else str(value) for value in expected) + "])"
            cases.append(DDBCase(f"{function}(col)", expected_text, f"col={flags_text}"))
        return cases
    if operation in {"binary.cross_above", "binary.cross_below"}:
        comparator = ">" if name == "cross_above" else "<"
        previous = "<=" if name == "cross_above" else ">="
        return [
            DDBCase(
                f"{function}(left, right)",
                f"(left {comparator} right) && (move(left, 1) {previous} move(right, 1))",
                _series_setup(seed),
            )
            for seed in range(10)
        ]

    cumulative = {
        "unary.cum_count": "cumcount(col)",
        "unary.cum_sum": "cumsum(col)",
        "unary.cum_prod": "cumprod(col)",
        "unary.cum_min": "cummin(col)",
        "unary.cum_max": "cummax(col)",
        "unary.cum_mean": "cumavg(col)",
        "unary.expanding_median": "cummed(col)",
        "unary.expanding_std": "cumstd(col)",
        "unary.expanding_var": "cumvar(col)",
    }
    if operation in cumulative:
        return [
            DDBCase(
                f"{function}(col, {1 + seed % 4})",
                f"iif(cumcount(col)<{1 + seed % 4}, NULL, {cumulative[operation]})",
                _series_setup(seed),
            )
            for seed in range(10)
        ]
    expanding_binary = {
        "binary.expanding_cov": "cumcovar(left, right)",
        "binary.expanding_corr": "cumcorr(left, right)",
        "binary.expanding_beta": "cumbeta(right, left)",
    }
    if operation in expanding_binary:
        return [
            DDBCase(
                f"{function}(left, right, {1 + seed % 4})",
                f"iif(cumcount(left)<{1 + seed % 4}, NULL, {expanding_binary[operation]})",
                _series_setup(seed),
            )
            for seed in range(10)
        ]
    if operation == "unary.expanding_sem":
        return [
            DDBCase(
                f"{function}(col, {1 + seed % 4})",
                f"iif(cumcount(col)<{1 + seed % 4}, NULL, cumstd(col)/sqrt(cumcount(col)))",
                _series_setup(seed),
            )
            for seed in range(10)
        ]
    if operation in {"unary.expanding_rank", "unary.expanding_rank_pct"}:
        percent = operation.endswith("_pct")
        ties = ["min", "max", "average", "dense"]
        cases = []
        for seed in range(10):
            minimum = 1 + seed % 4
            ascending = seed % 2 == 0
            tie = ties[seed % len(ties)]
            rank = (
                f"cumdenseRank(col, {'true' if ascending else 'false'}, true, {'true' if percent else 'false'})"
                if tie == "dense"
                else f"cumrank(col, {'true' if ascending else 'false'}, true, `{tie}, {'true' if percent else 'false'})"
            )
            if not percent:
                rank = f"({rank})+1"
            cases.append(
                DDBCase(
                    f'{function}(col, {minimum}, {str(ascending).lower()}, "{tie}")',
                    f"iif(cumcount(col)<{minimum}, NULL, {rank})",
                    _series_setup(seed),
                )
            )
        return cases
    if operation == "unary.expanding_quantile":
        return [
            DDBCase(
                f"{function}(col, {1 + seed % 4}, {0.1 * (seed + 1)})",
                f"iif(cumcount(col)<{1 + seed % 4}, NULL, cumpercentile(col, {0.1 * (seed + 1)}))",
                _series_setup(seed),
            )
            for seed in range(10)
        ]

    rolling = {
        "unary.rolling_count": "mcount(col, window, minimum)",
        "unary.rolling_sum": "msum(col, window, minimum)",
        "unary.rolling_prod": "mprod(col, window, minimum)",
        "unary.rolling_mean": "mavg(col, window, minimum)",
        "unary.rolling_median": "mmed(col, window, minimum)",
        "unary.rolling_std": "mstd(col, window, minimum)",
        "unary.rolling_var": "mvar(col, window, minimum)",
        "unary.rolling_mad": "mmad(col, window, true, minimum)",
        "unary.rolling_skew": "mskew(col, window, true, minimum)",
        "unary.rolling_kurt": "mkurtosis(col, window, true, minimum)",
        "unary.rolling_min": "mmin(col, window, minimum)",
        "unary.rolling_max": "mmax(col, window, minimum)",
        "unary.rolling_argmin": "mimin(col, window, minimum)",
        "unary.rolling_argmax": "mimax(col, window, minimum)",
        "unary.rolling_first": "mfirst(col, window, minimum)",
        "unary.rolling_last": "mlast(col, window, minimum)",
        "binary.rolling_cov": "mcovar(left, right, window, minimum)",
        "binary.rolling_corr": "mcorr(left, right, window, minimum)",
        "binary.rolling_beta": "mbeta(right, left, window, minimum)",
    }
    if operation in rolling:
        return [
            DDBCase(
                f"{function}({'left, right, ' if operation.startswith('binary.') else 'col, '}window, min_arg)",
                rolling[operation],
                _series_setup(seed) + f"; window={3 + seed % 5}; requested={1 + seed % (3 + seed % 5)}; min_arg={'int(NULL)' if seed % 2 == 0 else 'requested'}; minimum=iif(isNull(min_arg),window,min_arg)",
            )
            for seed in range(10)
        ]
    if operation in {"binary.rolling_alpha", "binary.rolling_residual"}:
        return [
            DDBCase(
                f"{function}(left, right, window, min_arg)",
                (
                    "mavg(right, window, minimum)-mbeta(right, left, window, minimum)*mavg(left, window, minimum)"
                    if operation.endswith("alpha")
                    else "right-(mavg(right, window, minimum)-mbeta(right, left, window, minimum)*mavg(left, window, minimum))-mbeta(right, left, window, minimum)*left"
                ),
                _series_setup(seed) + f"; window={3 + seed % 5}; requested={1 + seed % (3 + seed % 5)}; min_arg={'int(NULL)' if seed % 2 == 0 else 'requested'}; minimum=iif(isNull(min_arg),window,min_arg)",
            )
            for seed in range(10)
        ]
    if operation == "unary.rolling_sem":
        return [
            DDBCase(
                f"{function}(col, window, min_arg)",
                "mstd(col, window, minimum)/sqrt(mcount(col, window, minimum))",
                _series_setup(seed) + f"; window={3 + seed % 5}; requested={1 + seed % (3 + seed % 5)}; min_arg={'int(NULL)' if seed % 2 == 0 else 'requested'}; minimum=iif(isNull(min_arg),window,min_arg)",
            )
            for seed in range(10)
        ]
    if operation in {"unary.rolling_rank", "unary.rolling_rank_pct"}:
        percent = operation.endswith("_pct")
        ties = ["min", "max", "average"]
        cases = []
        for seed in range(10):
            window = 3 + seed % 5
            minimum = 1 + seed % window
            ascending = seed % 2 == 0
            tie = ties[seed % 3]
            expected = f"mrank(col, {str(ascending).lower()}, window, true, `{tie}, {str(percent).lower()}, minimum)"
            if not percent:
                expected = f"({expected})+1"
            cases.append(
                DDBCase(
                    f'{function}(col, window, min_arg, {str(ascending).lower()}, "{tie}")',
                    expected,
                    _series_setup(seed) + f"; window={window}; requested={minimum}; min_arg={'int(NULL)' if seed % 2 == 0 else 'requested'}; minimum=iif(isNull(min_arg),window,min_arg)",
                )
            )
        return cases
    if operation == "unary.rolling_quantile":
        return [
            DDBCase(
                f"{function}(col, window, min_arg, q)",
                'mpercentile(col, q, window, "linear", minimum)',
                _series_setup(seed) + f"; window={3 + seed % 5}; requested={1 + seed % (3 + seed % 5)}; min_arg={'int(NULL)' if seed % 2 == 0 else 'requested'}; minimum=iif(isNull(min_arg),window,min_arg); q={0.1 * (seed + 1)}",
            )
            for seed in range(10)
        ]
    if operation == "unary.rolling_zscore":
        return [
            DDBCase(
                f"{function}(col, window, min_arg)",
                "iif(mstd(col, window, minimum)==0, NULL, (col-mavg(col, window, minimum))/mstd(col, window, minimum))",
                _series_setup(seed) + f"; window={3 + seed % 5}; requested={1 + seed % (3 + seed % 5)}; min_arg={'int(NULL)' if seed % 2 == 0 else 'requested'}; minimum=iif(isNull(min_arg),window,min_arg)",
            )
            for seed in range(10)
        ]
    if operation in {"unary.rolling_true_count", "unary.rolling_any", "unary.rolling_all"}:
        cases = []
        for seed in range(10):
            window = 3 + seed % 5
            minimum = 1 + seed % window
            count_true = "msum(int(nullFill(col, false)), window, minimum)"
            expected = {
                "unary.rolling_true_count": count_true,
                "unary.rolling_any": f"({count_true})>0",
                "unary.rolling_all": f"(mcount(col, window, minimum)>=minimum)&&(({count_true})==mcount(col, window, minimum))",
            }[operation]
            cases.append(
                DDBCase(
                    f"{function}(col, window, min_arg)",
                    expected,
                    _series_setup(seed, boolean=True) + f"; window={window}; requested={minimum}; min_arg={'int(NULL)' if seed % 2 == 0 else 'requested'}; minimum=iif(isNull(min_arg),window,min_arg)",
                )
            )
        return cases
    if operation == "unary.decay_linear":
        return [
            DDBCase(
                f"{function}(col, window, min_arg)",
                "mavg(col, double(1..window), minimum)",
                _series_setup(seed) + f"; window={3 + seed % 5}; requested={1 + seed % (3 + seed % 5)}; min_arg={'int(NULL)' if seed % 2 == 0 else 'requested'}; minimum=iif(isNull(min_arg),window,min_arg)",
            )
            for seed in range(10)
        ]
    raise AssertionError(f"缺少 TS 用例：{operation}")


def _neutralize_cases(function: str) -> list[DDBCase]:
    """构造中性化函数的连续、分类和缺失值场景。"""
    return [
        DDBCase(
            "all(abs(result)<1e-10)",
            setup=f"x=double(1..10); y=2+3*x; controls=table(x as x); result={function}(y, controls, true)",
        ),
        DDBCase(
            "abs(avg(result))<1e-10 && abs(corr(result,x))<1e-10",
            setup=f"x=double(1..12); y=2+3*x+sin(x); controls=table(x as x); result={function}(y, controls, true)",
        ),
        DDBCase(
            "abs(avg(result[industry==`A]))<1e-10 && abs(avg(result[industry==`B]))<1e-10",
            setup=f"industry=`A`A`A`A`B`B`B`B; y=10 11 9 10 20 21 19 20.0; controls=table(industry as industry); result={function}(y, controls, true)",
        ),
        DDBCase(
            "abs(avg(result))<1e-10 && abs(corr(result,x))<1e-10 && abs(avg(result[industry==`A])-avg(result[industry==`B]))<1e-10",
            setup=f"x=double(1..12); industry=take(`A`B,12); y=2*x+iif(industry==`A,5.0,-3.0)+sin(x); controls=table(x as x,industry as industry); result={function}(y, controls, true)",
        ),
        DDBCase(
            "isNull(result[2]) && count(result)==9",
            setup=f"x=double(1..10); y=2+3*x; y[2]=NULL; controls=table(x as x); result={function}(y, controls, true)",
        ),
        DDBCase(
            "isNull(result[4]) && count(result)==9",
            setup=f"x=double(1..10); y=2+3*x; x[4]=NULL; controls=table(x as x); result={function}(y, controls, true)",
        ),
        DDBCase(
            "eqObj(result,y-avg(y))",
            setup=f"y=double(1..8); constant=take(1.0,8); controls=table(constant as constant); result={function}(y, controls, true)",
        ),
        DDBCase(
            "all(abs(result)<1e-10)",
            setup=f"y=take(7.0,1); x=take(2.0,1); controls=table(x as x); result={function}(y, controls, true)",
        ),
        DDBCase(
            "abs(avg(result[flag]))<1e-10 && abs(avg(result[!flag]))<1e-10",
            setup=f"flag=true true true false false false; y=10 11 9 20 19 21.0; controls=table(flag as flag); result={function}(y, controls, true)",
        ),
        DDBCase(
            "abs(sum(result*x))<1e-10",
            setup=f"x=double(1..10); y=3*x+sin(x); controls=table(x as x); result={function}(y, controls, false)",
        ),
    ]


def _cross_section_cases(model: Type[OperatorBase]) -> list[DDBCase]:
    """为一个 CS 算符构造十个纯函数场景。"""
    operation = _operation(model)
    function = model.function.name
    name = operation.split(".", 1)[1]
    if operation == "controls.neutralize_by":
        return _neutralize_cases(function)
    cases = []
    for seed in range(10):
        setup = (
            f"n={10 + seed}; col=double(1..n)+sin(double(1..n)+{seed}); "
            "left=col; right=2.5*col+cos(double(1..n))"
        )
        if operation in {"unary.demean", "grouped.demean"}:
            actual, expected = f"{function}(col)", "col-avg(col)"
        elif operation in {"unary.mean", "grouped.mean"}:
            actual, expected = f"{function}(col)", "take(avg(col),size(col))"
        elif operation in {"unary.zscore", "grouped.zscore"}:
            ddof = seed % 2
            scale = "stdp(col)" if ddof == 0 else "std(col)"
            actual, expected = f"{function}(col,{ddof})", f"(col-avg(col))/{scale}"
        elif operation == "unary.robust_zscore":
            scale = 1.0 + seed / 10
            actual, expected = f"{function}(col,{scale})", f"(col-med(col))/(mad(col,true)*{scale})"
        elif operation in {"unary.rank", "unary.rank_pct", "grouped.rank_pct"}:
            ascending = seed % 2 == 0
            ties = ["min", "max", "average", "first"][seed % 4]
            percent = operation.endswith("rank_pct")
            actual = f'{function}(col,{str(ascending).lower()},"{ties}")'
            expected = f"rank(col,{str(ascending).lower()},,true,`{ties},{str(percent).lower()})"
            if not percent:
                expected = f"({expected})+1"
        elif operation == "unary.rank_dense":
            ascending = seed % 2 == 0
            actual = f"{function}(col,{str(ascending).lower()})"
            expected = f"denseRank(col,{str(ascending).lower()},true,false)+1"
        elif operation == "unary.rank_normal":
            ascending = seed % 2 == 0
            actual = f"{function}(col,{str(ascending).lower()})"
            expected = f"invNormal(0,1,(rank(col,{str(ascending).lower()},,true,`average,false)+0.5)/count(col))"
        elif operation == "unary.qcut":
            q = 2 + seed % 5
            actual, expected = f"{function}(col,{q})", f"rank(col,true,{q},true,`min,false)"
        elif operation == "unary.winsorize":
            lower, upper = 0.05 + seed / 200, 0.95 - seed / 200
            actual = f"{function}(col,{lower},{upper})"
            expected = f"iif(col<quantile(col,{lower}),quantile(col,{lower}),iif(col>quantile(col,{upper}),quantile(col,{upper}),col))"
        elif operation == "unary.winsorize_mad":
            amount, scale = 2.0 + seed / 10, 1.0 + seed / 20
            actual = f"{function}(col,{amount},{scale})"
            expected = f"iif(col<med(col)-mad(col,true)*{scale}*{amount},med(col)-mad(col,true)*{scale}*{amount},iif(col>med(col)+mad(col,true)*{scale}*{amount},med(col)+mad(col,true)*{scale}*{amount},col))"
        elif operation in {"unary.normalize_sum", "unary.normalize_l1", "unary.normalize_l2"}:
            denominator = {"unary.normalize_sum": "sum(col)", "unary.normalize_l1": "sum(abs(col))", "unary.normalize_l2": "sqrt(sum(col*col))"}[operation]
            actual, expected = f"{function}(col)", f"col/{denominator}"
        elif operation in {"unary.count", "unary.sum", "unary.median", "unary.min", "unary.max", "unary.mad", "unary.skew", "unary.kurt"}:
            statistic = {"count": "count", "sum": "sum", "median": "med", "min": "min", "max": "max", "mad": "mad", "skew": "skew", "kurt": "kurtosis"}[name]
            call = f"{statistic}(col, true)" if name == "mad" else f"{statistic}(col)"
            actual, expected = f"{function}(col)", f"take({call},size(col))"
        elif operation in {"unary.std", "unary.var"}:
            ddof = seed % 2
            statistic = ("stdp" if ddof == 0 else "std") if name == "std" else ("covarp" if ddof == 0 else "covar")
            call = f"{statistic}(col)" if name == "std" else f"{statistic}(col,col)"
            actual, expected = f"{function}(col,{ddof})", f"take({call},size(col))"
        elif operation == "unary.quantile":
            q = 0.1 * (seed + 1)
            actual, expected = f"{function}(col,{q})", f"take(quantile(col,{q}),size(col))"
        elif operation in {"unary.top_n", "unary.bottom_n"}:
            amount = 1 + seed % 5
            ascending = operation.startswith("unary.bottom")
            actual = f"{function}(col,{amount})"
            expected = f"rank(col,{str(ascending).lower()},,true,`first,false)<{amount}"
        elif operation in {"unary.top_pct", "unary.bottom_pct"}:
            pct = 0.1 * (1 + seed % 5)
            ascending = operation.startswith("unary.bottom")
            actual = f"{function}(col,{pct})"
            expected = f"rank(col,{str(ascending).lower()},,true,`first,false)<ceil(count(col)*{pct})"
        elif operation in {"binary.corr", "binary.rank_corr", "binary.cov", "binary.beta", "binary.alpha", "binary.residual"}:
            actual = f"{function}(left,right)"
            variance = "covar(left,left)"
            slope = f"covar(left,right)/({variance})"
            expected = {
                "binary.corr": "take(corr(left,right),size(left))",
                "binary.rank_corr": "take(corr(rank(left),rank(right)),size(left))",
                "binary.cov": "take(covar(left,right),size(left))",
                "binary.beta": f"take({slope},size(left))",
                "binary.alpha": f"take(avg(right)-({slope})*avg(left),size(left))",
                "binary.residual": f"right-(avg(right)-({slope})*avg(left))-({slope})*left",
            }[operation]
        else:
            raise AssertionError(f"缺少 CS 用例：{operation}")
        cases.append(DDBCase(actual, expected, setup))
    return cases


MODELS = sorted(Derivative.operators.values(), key=lambda model: model.function.name)


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.function.name)
def test_operator_function(ddb_session, model: Type[OperatorBase]) -> None:
    """每个算符纯函数均执行十个输入输出场景。"""
    if issubclass(model, DirectOperator):
        cases = _direct_cases(model)
    elif issubclass(model, TimeSeriesOperator):
        cases = _time_series_cases(model)
    elif issubclass(model, CrossSectionOperator):
        cases = _cross_section_cases(model)
    else:
        raise AssertionError(model)
    assert_ddb_cases(ddb_session, model.function.name, cases)
