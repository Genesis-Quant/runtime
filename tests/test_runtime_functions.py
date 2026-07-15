"""验证 DolphinDB DSL 执行层公共函数。"""

import json

import pytest

from core.dolphindb.function import DolphinDBFunction
from core.dolphindb.runtime import RUNTIME_FUNCTIONS
from core.dolphindb.script import evaluator_functions

from .ddb_cases import DDBCase, assert_ddb_cases


TRUE_NODE = {
    "type": "DIRECT",
    "op": "nullary.true",
    "fields": {},
    "params": {},
}


def _ddb_json(value: object) -> str:
    """把 Python JSON 值转换为 DolphinDB fromStdJson 表达式。"""
    payload = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return f"fromStdJson({json.dumps(payload, ensure_ascii=False)})"


def _direct_node(
    operation: str,
    fields: dict[str, object],
    params: dict[str, object] | None = None,
) -> dict[str, object]:
    """构造执行层测试使用的 DIRECT 节点。"""
    return {
        "type": "DIRECT",
        "op": operation,
        "fields": fields,
        "params": params or {},
    }


def _source(seed: int = 0) -> str:
    """生成执行层测试使用的双股票行情表脚本。"""
    return (
        "source=table("
        "2024.01.01 2024.01.02 2024.01.03 2024.01.04 "
        "2024.01.01 2024.01.02 2024.01.03 2024.01.04 as time, "
        "`A`A`A`A`B`B`B`B as code, "
        f"double(1..8)+{seed} as x)"
    )


def _runtime_cases(function: DolphinDBFunction) -> list[DDBCase]:
    """为指定执行层函数构造十个输入输出场景。"""
    name = function.name
    if name == "normalize_on":
        cases = []
        for seed in range(10):
            n = 3 + seed
            if seed < 2:
                on = "true" if seed == 0 else "false"
                expected = f"take({on},{n})"
                setup = f"n={n}; on={on}"
            else:
                setup = f"n={n}; on=((0..(n-1)+{seed})%3)==0"
                if seed % 2 == 0:
                    setup += f"; on[{seed % n}]=NULL"
                expected = "nullFill(on,false)"
            cases.append(DDBCase(f"{name}(on,n)", expected, setup))
        return cases
    if name == "restore_masked_rows":
        return [
            DDBCase(
                f"{name}(selected,mask,n)",
                "expected",
                (
                    f"n={5 + seed}; mask=((0..(n-1)+{seed})%3)==0; full=double(1..n)+{seed}; "
                    "selected=full[mask]; expected=array(DOUBLE,n,n,NULL); "
                    "expected[(0..(n-1))[mask]]=selected"
                ),
            )
            for seed in range(10)
        ]
    if name in {"sample_operands", "select_operands"}:
        cases = []
        for seed in range(10):
            setup = (
                f"left=double(1..{6 + seed})+{seed}; right=((0..{5 + seed}+{seed})%2)==0; "
                "operands=array(ANY,0); operands.append!(left); operands.append!(right); "
                "expected=array(ANY,0)"
            )
            if name == "sample_operands":
                setup += "; expected.append!(take(left,1)); expected.append!(take(right,1))"
                actual = f"{name}(operands)"
            else:
                setup += "; mask=((0..(size(left)-1)+1)%3)==0; expected.append!(left[mask]); expected.append!(right[mask])"
                actual = f"{name}(operands,mask)"
            cases.append(DDBCase(actual, "expected", setup))
        return cases
    if name == "apply_time_series":
        return [
            DDBCase(
                f"{name}(cumavg,operands,on,code,time)",
                "expected",
                (
                    f"n={8 + 2 * seed}; value=double(1..n)+{seed}; code=take(`A`B,n); "
                    "time=2024.01.01+0..(n-1); on=((0..(n-1)+1)%3)!=0; "
                    "operands=array(ANY,0); operands.append!(value); mask=nullFill(on,false); "
                    "selected=contextby(cumavg,enlist(value[mask]),code[mask],time[mask]); "
                    "expected=array(DOUBLE,n,n,NULL); expected[(0..(n-1))[mask]]=selected"
                ),
            )
            for seed in range(10)
        ]
    if name == "apply_cross_section":
        return [
            DDBCase(
                f"{name}(runtime_test_demean,operands,on,time)",
                "expected",
                (
                    f"n={10 + 2 * seed}; value=double(1..n)+{seed}; time=take(2024.01.01 2024.01.02,n); "
                    "on=((0..(n-1)+1)%4)!=0; operands=array(ANY,0); operands.append!(value); "
                    "mask=nullFill(on,false); selected=contextby(runtime_test_demean,enlist(value[mask]),time[mask]); "
                    "expected=array(DOUBLE,n,n,NULL); expected[(0..(n-1))[mask]]=selected"
                ),
            )
            for seed in range(10)
        ]
    if name == "apply_grouped_cross_section":
        return [
            DDBCase(
                f"{name}(runtime_test_demean,operands,on,time,by)",
                "expected",
                (
                    f"n={12 + 2 * seed}; value=double(1..n)+{seed}; time=take(2024.01.01 2024.01.02,n); "
                    "by=take(`I1`I2,n); on=((0..(n-1)+1)%5)!=0; operands=array(ANY,0); operands.append!(value); "
                    "mask=nullFill(on,false)&&!isNull(by); selected=contextby(runtime_test_demean,enlist(value[mask]),(time[mask],by[mask])); "
                    "expected=array(DOUBLE,n,n,NULL); expected[(0..(n-1))[mask]]=selected"
                ),
            )
            for seed in range(10)
        ]
    if name == "apply_controlled_cross_section":
        return [
            DDBCase(
                f"{name}(runtime_test_control,target,controls,on,time)",
                "expected",
                (
                    f"n={10 + 2 * seed}; target=double(1..n)+{seed}; control=2*target; "
                    "controls=table(control as control); time=take(2024.01.01 2024.01.02,n); "
                    "on=((0..(n-1)+1)%4)!=0; mask=nullFill(on,false); expected=array(DOUBLE,n,n,NULL); "
                    "indices=(0..(n-1))[mask]; selected_time=time[mask]; "
                    "for(current_date in distinct(selected_time)){rows=indices[selected_time==current_date]; expected[rows]=target[rows]-avg(target[rows])}"
                ),
            )
            for seed in range(10)
        ]
    if name == "build_control_table":
        return [
            DDBCase(
                (
                    "eqObj(sort(columnNames(result)),sort(columnNames(expected)))&&"
                    "eqObj(result[`control0],expected[`control0])&&"
                    "eqObj(result[`control1],expected[`control1])"
                ),
                setup=(
                    f"x=double(1..{3 + seed}); category=take(`A`B,{3 + seed}); "
                    "values=array(ANY,0); values.append!(x); values.append!(category); "
                    f"expected=table(x as control0,category as control1); result={name}(values)"
                ),
            )
            for seed in range(10)
        ]
    if name == "require_key":
        return [
            DDBCase(
                f'{name}(object,"key{seed}","测试对象")',
                _ddb_json(seed),
                f'object={_ddb_json({f"key{seed}": seed, "other": seed + 1})}',
            )
            for seed in range(10)
        ]
    if name == "require_vector":
        return [
            DDBCase(
                f'{name}(value,n,"测试值")',
                "expected",
                (
                    f"n={seed + 1}; value={'double(' + str(seed) + ')' if seed % 2 == 0 else 'double(1..n)'}; "
                    "expected=iif(is_scalar_form(value),take(value,n),value)"
                ),
            )
            for seed in range(10)
        ]
    if name == "require_column":
        return [
            DDBCase(
                f'{name}(source,"value{seed}","测试算符")',
                f"source[`value{seed}]",
                f"source=table(double(1..{seed + 2}) as value{seed})",
            )
            for seed in range(10)
        ]
    if name == "evaluate_operand":
        cases = []
        for seed in range(10):
            node = _direct_node("binary.add", {"left": "x", "right": seed})
            definitions = {"named": node}
            operand: object = "x" if seed % 3 == 0 else ("named" if seed % 3 == 1 else node)
            cases.append(
                DDBCase(
                    f"{name}(evaluate_node,source,definitions,cache,states,operand)",
                    "x" if seed % 3 == 0 else f"x+{seed}",
                    (
                        f"{_source(seed)}; x=source[`x]; definitions={_ddb_json(definitions)}; "
                        f"operand={_ddb_json(operand)}; cache=dict(STRING,ANY); states=dict(STRING,INT)"
                    ),
                )
            )
        return cases
    if name == "evaluate_operands":
        cases = []
        for seed in range(10):
            node = _direct_node("binary.add", {"left": "x", "right": seed})
            operands = ["x", seed, node]
            setup = (
                f"{_source(seed)}; x=source[`x]; definitions=dict(STRING,ANY); operands={_ddb_json(operands)}; "
                "cache=dict(STRING,ANY); states=dict(STRING,INT); expected=array(ANY,0); "
                f"expected.append!(x); expected.append!(operands[1]); expected.append!(x+{seed})"
            )
            cases.append(DDBCase(f"{name}(evaluate_node,source,definitions,cache,states,operands)", "expected", setup))
        return cases
    if name == "evaluate_fields":
        cases = []
        for seed in range(10):
            node = _direct_node("binary.add", {"left": "x", "right": seed})
            fields = {"left": "x", "right": node, "cols": ["x", seed]}
            setup = (
                f"{_source(seed)}; x=source[`x]; definitions=dict(STRING,ANY); fields={_ddb_json(fields)}; "
                "cache=dict(STRING,ANY); states=dict(STRING,INT); "
                f"result={name}(evaluate_node,source,definitions,cache,states,fields)"
            )
            actual = (
                f'eqObj(result["left"],x)&&eqObj(result["right"],x+{seed})&&'
                'eqObj(result["cols"][0],x)&&eqObj(result["cols"][1],fields["cols"][1])'
            )
            cases.append(DDBCase(actual, setup=setup))
        return cases
    if name == "evaluate_definition":
        return [
            DDBCase(
                f'{name}(evaluate_node,source,definitions,cache,states,"factor")',
                f"source[`x]+{seed}",
                (
                    f"{_source(seed)}; definitions={_ddb_json({'factor': _direct_node('binary.add', {'left': 'x', 'right': seed})})}; "
                    "cache=dict(STRING,ANY); states=dict(STRING,INT)"
                ),
            )
            for seed in range(10)
        ]
    if name == "evaluate_node":
        return _evaluate_node_cases(name)
    if name == "parse_definitions":
        cases = []
        for seed in range(10):
            definitions = {f"factor{seed}": _direct_node("binary.add", {"left": "x", "right": seed})}
            parsed = _ddb_json(definitions)
            source = json.dumps(json.dumps(definitions, separators=(",", ":"))) if seed % 2 == 0 else parsed
            cases.append(
                DDBCase(
                    "toStdJson(result)==toStdJson(expected)",
                    setup=f"result={name}({source}); expected={parsed}",
                )
            )
        return cases
    if name == "compute_factors":
        cases = []
        for seed in range(10):
            definitions = {
                "first": _direct_node("binary.add", {"left": "x", "right": seed}),
                "second": _direct_node("binary.mul", {"left": "first", "right": 2}),
            }
            setup = f"{_source(seed)}; definitions={_ddb_json(definitions)}; result={name}(source,definitions)"
            cases.append(DDBCase(f'eqObj(result["first"],source[`x]+{seed})&&eqObj(result["second"],2*(source[`x]+{seed}))', setup=setup))
        return cases
    raise AssertionError(f"缺少执行层函数用例：{name}")


def _evaluate_node_cases(function_name: str) -> list[DDBCase]:
    """构造 DIRECT、TS 和 CS 节点的递归执行场景。"""
    cases = []
    for seed in range(10):
        if seed % 3 == 0:
            node = _direct_node("binary.add", {"left": "x", "right": seed})
            expected = f"source[`x]+{seed}"
        elif seed % 3 == 1:
            node = {
                "type": "TS",
                "op": "unary.rolling_mean",
                "fields": {"col": "x"},
                "params": {"window": 2, "min_periods": 1},
                "on": TRUE_NODE,
            }
            expected = "contextby(mavg{,2,1},enlist(source[`x]),source[`code],source[`time])"
        else:
            node = {
                "type": "CS",
                "op": "unary.demean",
                "fields": {"col": "x"},
                "params": {},
                "on": TRUE_NODE,
            }
            expected = "contextby(runtime_test_demean,enlist(source[`x]),source[`time])"
        setup = f"{_source(seed)}; definitions=dict(STRING,ANY); node={_ddb_json(node)}; cache=dict(STRING,ANY); states=dict(STRING,INT)"
        cases.append(DDBCase(f"{function_name}(source,definitions,cache,states,node)", expected, setup))
    return cases


def _evaluator_cases(function: DolphinDBFunction) -> list[DDBCase]:
    """为自动生成的分类分发函数构造十个场景。"""
    name = function.name
    cases = []
    for seed in range(10):
        if name == "evaluate_direct":
            operation = ["binary.add", "binary.sub", "binary.mul"][seed % 3]
            node = _direct_node(operation, {"left": "x", "right": seed + 1})
            symbol = {"binary.add": "+", "binary.sub": "-", "binary.mul": "*"}[operation]
            expected = f"source[`x]{symbol}{seed + 1}"
        elif name == "evaluate_time_series":
            window = 2 + seed % 3
            node = {
                "type": "TS",
                "op": "unary.rolling_mean",
                "fields": {"col": "x"},
                "params": {"window": window, "min_periods": 1},
                "on": TRUE_NODE,
            }
            expected = f"contextby(mavg{{,{window},1}},enlist(source[`x]),source[`code],source[`time])"
        else:
            node = {
                "type": "CS",
                "op": "unary.demean",
                "fields": {"col": "x"},
                "params": {},
                "on": TRUE_NODE,
            }
            expected = "contextby(runtime_test_demean,enlist(source[`x]),source[`time])"
        setup = f"{_source(seed)}; definitions=dict(STRING,ANY); node={_ddb_json(node)}; cache=dict(STRING,ANY); states=dict(STRING,INT)"
        cases.append(DDBCase(f"{name}(evaluate_node,source,definitions,cache,states,node)", expected, setup))
    return cases


@pytest.fixture(scope="module", autouse=True)
def runtime_test_helpers(ddb_session) -> None:
    """加载执行层测试使用的简单组内函数。"""
    ddb_session.run(
        """
def runtime_test_demean(value) {
    return value - avg(value)
}

def runtime_test_control(target, controls) {
    return target - avg(target)
}
"""
    )


@pytest.mark.parametrize("function", RUNTIME_FUNCTIONS, ids=lambda function: function.name)
def test_runtime_function(ddb_session, function: DolphinDBFunction) -> None:
    """每个执行层公共函数均执行十个场景。"""
    assert_ddb_cases(ddb_session, function.name, _runtime_cases(function))


@pytest.mark.parametrize("function", evaluator_functions(), ids=lambda function: function.name)
def test_generated_evaluator(ddb_session, function: DolphinDBFunction) -> None:
    """三类自动分发函数均执行十个场景。"""
    assert_ddb_cases(ddb_session, function.name, _evaluator_cases(function))
