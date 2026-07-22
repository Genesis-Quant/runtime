"""验证 DolphinDB DSL 运行时的分组、递归、广播和错误语义。"""

import json

import numpy as np
import pandas as pd
import pytest

from tests.support.assertions import assert_vector_equal
from tests.support.dsl import (
    TRUE_NODE,
    compute_factors,
    cross_section,
    direct,
    run_uploaded,
    time_series,
)


def _ddb_json(value: object) -> str:
    """把 Python 对象转换为 DolphinDB 标准 JSON 表达式。"""
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return f"fromStdJson({json.dumps(payload, ensure_ascii=False)})"


def _runtime_state(definitions: dict[str, object] | None = None) -> str:
    """构造递归执行函数所需的 definitions、cache 和 states。"""
    serialized = _ddb_json({} if definitions is None else definitions)
    return (
        f"definitions={serialized};"
        "cache=dict(STRING,ANY);"
        "states=dict(STRING,INT)"
    )


def test_normalize_on_broadcasts_and_fills_nulls(ddb_session) -> None:
    """BOOL 标量会广播，BOOL 向量中的 NULL 会被视为 false。"""
    assert_vector_equal(ddb_session.run("normalize_on(true, 4)"), [True] * 4)
    assert_vector_equal(ddb_session.run("normalize_on(false, 3)"), [False] * 3)
    assert_vector_equal(
        ddb_session.run("normalize_on(bool(NULL), 3)"),
        [False, False, False],
    )
    assert_vector_equal(
        ddb_session.run("normalize_on(true NULL false true, 4)"),
        [True, False, False, True],
    )
    assert_vector_equal(ddb_session.run("normalize_on(true, 0)"), [])


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("normalize_on(1, 3)", "on 必须是 BOOL"),
        ("normalize_on(true false, 3)", "长度为 3"),
        ("normalize_on(matrix(true false, false true), 4)", "BOOL 向量"),
    ],
)
def test_normalize_on_rejects_invalid_type_or_shape(
    ddb_session,
    expression: str,
    message: str,
) -> None:
    """非 BOOL、矩阵和长度不匹配的 on 都应给出定位明确的错误。"""
    with pytest.raises(RuntimeError, match=message):
        ddb_session.run(expression)


def test_restore_masked_rows_preserves_positions_and_types(ddb_session) -> None:
    """回填只写入 true 位置，并保留 DOUBLE、SYMBOL 和 BOOL 类型。"""
    actual = ddb_session.run(
        "restore_masked_rows(10.5 20.5 30.5, true false true false true, 5)"
    )
    assert_vector_equal(actual, [10.5, np.nan, 20.5, np.nan, 30.5])

    symbols = ddb_session.run(
        'restore_masked_rows(symbol(["bank","tech"]), true false true, 3)'
    )
    assert symbols.tolist() == ["bank", "", "tech"]
    assert_vector_equal(
        ddb_session.run(
            'isNull(restore_masked_rows(symbol(["bank","tech"]), true false true, 3))'
        ),
        [False, True, False],
    )
    assert ddb_session.run(
        'typestr(restore_masked_rows(symbol(["bank","tech"]), true false true, 3))'
    ) == "FAST SYMBOL VECTOR"

    booleans = ddb_session.run(
        "restore_masked_rows(true false, true false true, 3)"
    )
    assert_vector_equal(booleans, [True, None, False])


def test_restore_masked_rows_handles_empty_selection_and_table(ddb_session) -> None:
    """零行和全 false 掩码返回同类型全空向量，表型结果不能被误用。"""
    assert_vector_equal(
        ddb_session.run(
            "restore_masked_rows(double([]), false false false, 3)"
        ),
        [np.nan, np.nan, np.nan],
    )
    assert_vector_equal(
        ddb_session.run("restore_masked_rows(double([]), bool([]), 0)"),
        [],
    )
    with pytest.raises(RuntimeError):
        ddb_session.run(
            "restore_masked_rows(table(1 2 as x), true false, 2)"
        )


def test_operand_collection_helpers_preserve_order_and_types(ddb_session) -> None:
    """采样与筛选必须按原顺序处理混合类型操作数。"""
    ddb_session.run(
        """
runtime_operands=array(ANY,0)
runtime_operands.append!(1.5 2.5 3.5 4.5)
runtime_operands.append!(`A`B`C`D)
runtime_operands.append!(true false NULL true)
runtime_sample=sample_operands(runtime_operands)
runtime_selected=select_operands(runtime_operands, true false true false)
"""
    )
    assert_vector_equal(ddb_session.run("runtime_sample[0]"), [1.5])
    assert_vector_equal(ddb_session.run("runtime_sample[1]"), ["A"])
    assert_vector_equal(ddb_session.run("runtime_sample[2]"), [True])
    assert_vector_equal(ddb_session.run("runtime_selected[0]"), [1.5, 3.5])
    assert_vector_equal(ddb_session.run("runtime_selected[1]"), ["A", "C"])
    assert_vector_equal(ddb_session.run("runtime_selected[2]"), [True, None])
    assert ddb_session.run("size(sample_operands(array(ANY,0)))") == 0
    assert ddb_session.run(
        "size(select_operands(array(ANY,0), bool([])))"
    ) == 0
    ddb_session.run(
        """
empty_operands=array(ANY,0)
empty_operands.append!(double([]))
empty_operands.append!(symbol([]))
empty_operands.append!(bool([]))
empty_samples=sample_operands(empty_operands)
"""
    )
    assert_vector_equal(ddb_session.run("each(size, empty_samples)"), [1, 1, 1])
    assert list(ddb_session.run("each(typestr, empty_samples)")) == ["ANY VECTOR"] * 3
    for index in range(3):
        assert_vector_equal(
            ddb_session.run(f"isNull(empty_samples[{index}])"),
            [True],
        )


def test_apply_time_series_sorts_within_code_and_restores_rows(ddb_session) -> None:
    """TS 执行器只使用 on=true 行，并按股票和时间计算后回到原行序。"""
    actual = run_uploaded(
        ddb_session,
        (
            "apply_time_series(ts_unary_cum_sum{,1}, enlist(runtime_value), "
            "runtime_on, runtime_code, runtime_time, double([]))"
        ),
        runtime_value=np.array([10.0, 1.0, 3.0, 5.0, 2.0, 4.0]),
        runtime_on=np.array([True, True, False, True, True, None], dtype=object),
        runtime_code=np.array(["A", "A", "A", "B", "B", "B"]),
        runtime_time=pd.to_datetime(
            ["2024-01-03", "2024-01-01", "2024-01-02", "2024-01-02", "2024-01-01", "2024-01-03"]
        ),
    )
    assert_vector_equal(actual, [11.0, 1.0, np.nan, 7.0, 2.0, np.nan])


def test_apply_time_series_empty_selection_keeps_output_contract(ddb_session) -> None:
    """没有选中行时仍返回与输入等长、类型正确的全 NULL 结果。"""
    actual = ddb_session.run(
        "value=1.0 2.0 3.0; operands=enlist(value);"
        "apply_time_series(ts_unary_cum_sum{,1}, operands, false, `A`A`A, 2024.01.01+0..2, double([]))"
    )
    assert_vector_equal(actual, [np.nan, np.nan, np.nan])
    assert ddb_session.run(
        "value=1.0 2.0; operands=enlist(value);"
        "typestr(apply_time_series(ts_unary_changed{,false}, operands, false, `A`A, 2024.01.01+0..1, bool([])))"
    ) == "FAST BOOL VECTOR"


def test_apply_cross_section_groups_by_date_and_restores_rows(ddb_session) -> None:
    """普通截面执行器应按日期独立计算并保留未选中行为空。"""
    actual = run_uploaded(
        ddb_session,
        (
            "apply_cross_section(cs_unary_demean, enlist(runtime_cs_value), "
            "runtime_cs_on, runtime_cs_time, double([]))"
        ),
        runtime_cs_value=np.array([1.0, 3.0, 5.0, 10.0, 14.0, 20.0]),
        runtime_cs_on=np.array([True, False, True, True, True, None], dtype=object),
        runtime_cs_time=pd.to_datetime(
            ["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-02", "2024-01-03", "2024-01-03"]
        ),
    )
    assert_vector_equal(actual, [-4.5, np.nan, -4.5, 4.5, 4.5, np.nan])
    empty = ddb_session.run(
        "value=1.0 2.0; operands=enlist(value);"
        "apply_cross_section(cs_unary_demean, operands, false, 2024.01.01 2024.01.02, double([]))"
    )
    assert_vector_equal(empty, [np.nan, np.nan])


def test_apply_grouped_cross_section_excludes_null_group_and_on(ddb_session) -> None:
    """分组截面同时按日期和分类计算，并排除空分类与 on=false 行。"""
    actual = run_uploaded(
        ddb_session,
        (
            "apply_grouped_cross_section(cs_grouped_demean, enlist(runtime_group_value), "
            "runtime_group_on, runtime_group_time, runtime_group_by, double([]))"
        ),
        runtime_group_value=np.array([1.0, 3.0, 6.0, 8.0, 5.0, 7.0, 9.0, 13.0]),
        runtime_group_on=np.array([True, True, True, True, True, False, True, True]),
        runtime_group_time=pd.to_datetime(["2024-01-02"] * 4 + ["2024-01-03"] * 4),
        runtime_group_by=np.array(["A", "A", "B", None, "A", "A", "B", "B"], dtype=object),
    )
    assert_vector_equal(actual, [-1.0, 1.0, 0.0, np.nan, 0.0, np.nan, -2.0, 2.0])

    empty = ddb_session.run(
        "value=1.0 2.0; operands=enlist(value); by=array(STRING,2,2,NULL);"
        "apply_grouped_cross_section(cs_grouped_demean, operands, true, 2024.01.01 2024.01.01, by, double([]))"
    )
    assert_vector_equal(empty, [np.nan, np.nan])


def test_apply_controlled_cross_section_runs_each_date_independently(ddb_session) -> None:
    """控制变量截面按日回归，on=false 与控制变量缺失行保持 NULL。"""
    source = pd.DataFrame(
        {
            "target": [3.0, 5.0, 7.0, 4.0, 8.0, 12.0, 99.0],
            "size": [1.0, 2.0, 3.0, 1.0, 2.0, 3.0, 4.0],
            "industry": ["A", "A", "A", "B", "B", "B", "B"],
            "time": pd.to_datetime(["2024-01-02"] * 3 + ["2024-01-03"] * 4),
            "on": [True, True, True, True, True, True, False],
        }
    )
    ddb_session.upload({"runtime_control_source": source})
    actual = ddb_session.run(
        "controls=select size,industry from runtime_control_source;"
        "apply_controlled_cross_section(cs_controls_neutralize_by{,,true}, "
        "runtime_control_source.target, controls, runtime_control_source.on, runtime_control_source.time)"
    )
    assert_vector_equal(actual, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, np.nan], atol=1e-10)

    empty = ddb_session.run(
        "target=1.0 2.0; controls=table(3.0 4.0 as size);"
        "apply_controlled_cross_section(cs_controls_neutralize_by{,,true}, target, controls, false, 2024.01.01 2024.01.02)"
    )
    assert_vector_equal(empty, [np.nan, np.nan])


def test_build_control_table_handles_mixed_controls_and_rejects_empty(ddb_session) -> None:
    """控制变量按位置命名并保留值，空输入返回明确的契约错误。"""
    ddb_session.run(
        "values=array(ANY,0);values.append!(1.0 2.0 3.0);"
        "values.append!(`bank`tech`bank);values.append!(true false true);"
        "runtime_controls=build_control_table(values)"
    )
    assert sorted(ddb_session.run("columnNames(runtime_controls)").tolist()) == [
        "control0",
        "control1",
        "control2",
    ]
    assert_vector_equal(ddb_session.run("runtime_controls.control0"), [1.0, 2.0, 3.0])
    assert_vector_equal(ddb_session.run("runtime_controls.control1"), ["bank", "tech", "bank"])
    assert_vector_equal(ddb_session.run("runtime_controls.control2"), [True, False, True])
    with pytest.raises(RuntimeError, match="控制变量至少包含一列"):
        ddb_session.run("build_control_table(array(ANY,0))")


def test_require_key_reports_form_and_missing_key(ddb_session) -> None:
    """字典读取成功，其余形态或缺键错误必须包含调用位置。"""
    assert ddb_session.run(
        'object=dict(["x"], [42]); require_key(object, "x", "测试节点")'
    ) == 42
    with pytest.raises(RuntimeError, match="测试节点 必须是字典"):
        ddb_session.run('require_key(1 2, "x", "测试节点")')
    with pytest.raises(RuntimeError, match="测试节点 缺少必填键 x"):
        ddb_session.run(
            'object=dict(["y"], [42]); require_key(object, "x", "测试节点")'
        )


def test_require_vector_broadcasts_only_supported_shapes(ddb_session) -> None:
    """标量和单元素向量可广播，等长向量原样返回，其他形态被拒绝。"""
    assert_vector_equal(ddb_session.run('require_vector(7, 3, "值")'), [7, 7, 7])
    assert_vector_equal(
        ddb_session.run('require_vector(symbol(enlist("bank")), 3, "值")'),
        ["bank", "bank", "bank"],
    )
    assert_vector_equal(ddb_session.run('require_vector(1 2 3, 3, "值")'), [1, 2, 3])
    assert_vector_equal(ddb_session.run('require_vector(7, 0, "值")'), [])
    with pytest.raises(RuntimeError, match="值 必须返回长度为 3 的向量"):
        ddb_session.run('require_vector(1 2, 3, "值")')
    with pytest.raises(RuntimeError, match="值 必须返回长度为 4 的向量"):
        ddb_session.run('require_vector(matrix(1 2, 3 4), 4, "值")')


def test_require_column_returns_values_and_names_missing_column(ddb_session) -> None:
    """必需列读取应保留向量，缺列错误应同时包含算符和列名。"""
    assert_vector_equal(
        ddb_session.run(
            'source=table(1.0 2.0 as value);require_column(source,"value","unary.test")'
        ),
        [1.0, 2.0],
    )
    with pytest.raises(RuntimeError, match="unary.test 要求输入表包含列 code"):
        ddb_session.run(
            'source=table(1.0 2.0 as value);require_column(source,"code","unary.test")'
        )


def test_evaluate_operand_resolves_every_operand_kind(ddb_session) -> None:
    """嵌套节点、命名因子、列名和标量应走各自分支，SYMBOL 字面量会广播。"""
    nested = direct("binary.add", {"left": "x", "right": 2})
    named = direct("binary.mul", {"left": nested, "right": 3})
    definitions = {"named": named}
    setup = (
        "source=table(1.0 2.0 3.0 as x);"
        f"{_runtime_state(definitions)};"
    )
    assert_vector_equal(
        ddb_session.run(
            setup
            + 'evaluate_operand(evaluate_node,source,definitions,cache,states,"x")'
        ),
        [1.0, 2.0, 3.0],
    )
    assert_vector_equal(
        ddb_session.run(
            setup
            + 'evaluate_operand(evaluate_node,source,definitions,cache,states,"named")'
        ),
        [9.0, 12.0, 15.0],
    )
    assert_vector_equal(
        ddb_session.run(
            setup
            + f"operand={_ddb_json(nested)};"
            "evaluate_operand(evaluate_node,source,definitions,cache,states,operand)"
        ),
        [3.0, 4.0, 5.0],
    )
    assert ddb_session.run(
        setup + "evaluate_operand(evaluate_node,source,definitions,cache,states,7)"
    ) == 7

    symbol_node = direct(
        "nullary.literal",
        {},
        {"value": "bank", "dtype": "symbol"},
    )
    assert_vector_equal(
        ddb_session.run(
            setup
            + f"operand={_ddb_json(symbol_node)};"
            "evaluate_operand(evaluate_node,source,definitions,cache,states,operand)"
        ),
        ["bank", "bank", "bank"],
    )


def test_evaluate_operand_rejects_missing_names_and_raw_vectors(ddb_session) -> None:
    """未知字符串与 JSON 外部直接传入的向量都不能绕过操作数协议。"""
    setup = "source=table(1 2 as x);" + _runtime_state() + ";"
    with pytest.raises(RuntimeError, match="不存在的列或命名因子 missing"):
        ddb_session.run(
            setup
            + 'evaluate_operand(evaluate_node,source,definitions,cache,states,"missing")'
        )
    with pytest.raises(RuntimeError, match="DSL 操作数必须是"):
        ddb_session.run(
            setup
            + "evaluate_operand(evaluate_node,source,definitions,cache,states,1 2)"
        )


def test_evaluate_operands_and_fields_preserve_structure(ddb_session) -> None:
    """复数操作数和字段字典应保留名称、顺序及嵌套求值结果。"""
    nested = direct("binary.add", {"left": "x", "right": 10})
    fields = {"left": "x", "right": nested, "cols": ["x", 4]}
    setup = (
        "source=table(1.0 2.0 3.0 as x);"
        f"{_runtime_state()};"
        f"fields={_ddb_json(fields)};"
        "result=evaluate_fields(evaluate_node,source,definitions,cache,states,fields);"
    )
    ddb_session.run(setup)
    assert_vector_equal(ddb_session.run('result["left"]'), [1.0, 2.0, 3.0])
    assert_vector_equal(ddb_session.run('result["right"]'), [11.0, 12.0, 13.0])
    assert_vector_equal(ddb_session.run('result["cols"][0]'), [1.0, 2.0, 3.0])
    assert ddb_session.run('result["cols"][1]') == 4

    operands = ["x", 5, nested]
    ddb_session.run(
        "source=table(1.0 2.0 as x);"
        f"{_runtime_state()};operands={_ddb_json(operands)};"
        "result=evaluate_operands(evaluate_node,source,definitions,cache,states,operands)"
    )
    assert_vector_equal(ddb_session.run("result[0]"), [1.0, 2.0])
    assert ddb_session.run("result[1]") == 5
    assert_vector_equal(ddb_session.run("result[2]"), [11.0, 12.0])

    with pytest.raises(RuntimeError, match="DSL fields 必须是字典"):
        ddb_session.run(
            "source=table(1 2 as x);"
            f"{_runtime_state()};"
            "evaluate_fields(evaluate_node,source,definitions,cache,states,1 2)"
        )


def test_evaluate_definition_caches_results_and_detects_cycles(ddb_session) -> None:
    """命名因子只计算一次，完成状态为 2，递归环和缺失名称必须报错。"""
    definitions = {
        "base": direct("binary.add", {"left": "x", "right": 1}),
        "result": direct("binary.add", {"left": "base", "right": "base"}),
    }
    ddb_session.run(
        "source=table(1.0 2.0 3.0 as x);"
        f"{_runtime_state(definitions)};"
        'runtime_factor=evaluate_definition(evaluate_node,source,definitions,cache,states,"result")'
    )
    assert_vector_equal(ddb_session.run("runtime_factor"), [4.0, 6.0, 8.0])
    assert ddb_session.run('states["base"]') == 2
    assert ddb_session.run('states["result"]') == 2
    assert ddb_session.run("size(cache)") == 2

    cached = ddb_session.run(
        "source=table(1 2 as x);definitions=dict(STRING,ANY);"
        'cache=dict(["ready"], [9 8]);states=dict(STRING,INT);'
        'evaluate_definition(evaluate_node,source,definitions,cache,states,"ready")'
    )
    assert_vector_equal(cached, [9, 8])

    cycle = {
        "left": direct("binary.add", {"left": "right", "right": 1}),
        "right": direct("binary.add", {"left": "left", "right": 1}),
    }
    with pytest.raises(RuntimeError, match="循环依赖.*left"):
        ddb_session.run(
            "source=table(1 2 as x);"
            f"{_runtime_state(cycle)};"
            'evaluate_definition(evaluate_node,source,definitions,cache,states,"left")'
        )
    with pytest.raises(RuntimeError, match="不存在命名因子 missing"):
        ddb_session.run(
            "source=table(1 2 as x);"
            f"{_runtime_state()};"
            'evaluate_definition(evaluate_node,source,definitions,cache,states,"missing")'
        )


def test_evaluate_definition_broadcasts_scalars_and_single_symbol_vectors(ddb_session) -> None:
    """命名字面量最终必须规范为表行数长度，包括 DolphinDB 无标量形态的 SYMBOL。"""
    definitions = {
        "number": direct("nullary.literal", {}, {"value": 7, "dtype": "int"}),
        "industry": direct(
            "nullary.literal",
            {},
            {"value": "bank", "dtype": "symbol"},
        ),
    }
    result = compute_factors(
        ddb_session,
        pd.DataFrame({"x": [1.0, 2.0, 3.0]}),
        definitions,
    )
    assert_vector_equal(result["number"], [7, 7, 7])
    assert_vector_equal(result["industry"], ["bank", "bank", "bank"])


@pytest.mark.parametrize(
    ("node", "message"),
    [
        ({"op": "binary.add", "fields": {}, "params": {}}, "缺少必填键 type"),
        ({"type": "DIRECT", "fields": {}, "params": {}}, "缺少必填键 op"),
        ({"type": "DIRECT", "op": "binary.add", "params": {}}, "缺少必填键 fields"),
        ({"type": "DIRECT", "op": "binary.add", "fields": {}}, "缺少必填键 params"),
        (
            {"type": "DIRECT", "op": "binary.add", "fields": {}, "params": {}, "on": True},
            "DIRECT 节点禁止包含 on",
        ),
        ({"type": "TS", "op": "unary.diff", "fields": {}, "params": {}}, "TS 节点 缺少必填键 on"),
        ({"type": "CS", "op": "unary.mean", "fields": {}, "params": {}}, "CS 节点 缺少必填键 on"),
        ({"type": "OTHER", "op": "x", "fields": {}, "params": {}}, "未知 DSL 类型 OTHER"),
    ],
)
def test_evaluate_node_rejects_invalid_common_structure(
    ddb_session,
    node: dict[str, object],
    message: str,
) -> None:
    """运行时不能信任外部 JSON，公共必填键、on 和类别仍需完整校验。"""
    with pytest.raises(RuntimeError, match=message):
        ddb_session.run(
            "source=table(1 2 as x);"
            f"{_runtime_state()};node={_ddb_json(node)};"
            "evaluate_node(source,definitions,cache,states,node)"
        )


def test_evaluate_node_dispatches_direct_ts_and_cs(ddb_session) -> None:
    """三类节点都应经统一递归入口得到与独立计算一致的结果。"""
    source = pd.DataFrame(
        {
            "time": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-01", "2024-01-02"]),
            "code": ["A", "A", "B", "B"],
            "x": [1.0, 3.0, 10.0, 14.0],
        }
    )
    definitions = {
        "direct_result": direct("binary.add", {"left": "x", "right": 2}),
        "ts_result": time_series(
            "unary.diff",
            {"col": "x"},
            {"periods": 1},
            on=TRUE_NODE,
        ),
        "cs_result": cross_section("unary.demean", {"col": "x"}, on=TRUE_NODE),
    }
    result = compute_factors(ddb_session, source, definitions)
    assert_vector_equal(result["direct_result"], [3.0, 5.0, 12.0, 16.0])
    assert_vector_equal(result["ts_result"], [np.nan, 2.0, np.nan, 4.0])
    assert_vector_equal(result["cs_result"], [-4.5, -5.5, 4.5, 5.5])


def test_generated_evaluators_reject_unknown_ops_and_bad_inputs(ddb_session) -> None:
    """自动生成的三类分发器必须拒绝未知算符、缺少键列和错误字段长度。"""
    cases = [
        (
            {"type": "DIRECT", "op": "missing.direct", "fields": {}, "params": {}},
            "未实现 DIRECT 算符 missing.direct",
        ),
        (
            {"type": "TS", "op": "missing.ts", "fields": {}, "params": {}, "on": True},
            "missing.ts 要求输入表包含列 code",
        ),
        (
            {"type": "CS", "op": "missing.cs", "fields": {}, "params": {}, "on": True},
            "missing.cs 要求输入表包含列 time",
        ),
    ]
    for node, message in cases:
        with pytest.raises(RuntimeError, match=message):
            ddb_session.run(
                "source=table(1 2 as x);"
                f"{_runtime_state()};node={_ddb_json(node)};"
                "evaluate_node(source,definitions,cache,states,node)"
            )

    bad_length = {
        "type": "TS",
        "op": "unary.diff",
        "fields": {"col": [1, 2]},
        "params": {"periods": 1},
        "on": True,
    }
    source = pd.DataFrame(
        {
                "time": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
                "code": ["A", "A", "A"],
                "x": [1.0, 2.0, 3.0],
        }
    )
    ddb_session.upload({"runtime_bad_source": source})
    with pytest.raises(RuntimeError, match="unary.diff.fields.col 必须返回长度为 3 的向量"):
        ddb_session.run(
            f"node={_ddb_json(bad_length)};{_runtime_state()};"
            "evaluate_node(runtime_bad_source,definitions,cache,states,node)"
        )


def test_parse_definitions_accepts_json_and_any_dictionary(ddb_session) -> None:
    """定义集合支持 JSON 字符串和 ANY 字典，并拒绝其他形态与强类型字典。"""
    definitions = {"factor": direct("binary.add", {"left": "x", "right": 1})}
    expression = _ddb_json(definitions)
    assert ddb_session.run(
        f"parsed=parse_definitions({expression});string(parsed.keys())"
    ) == ["factor"]

    json_text = json.dumps(definitions, separators=(",", ":"))
    assert ddb_session.run(
        f"parsed=parse_definitions({json.dumps(json_text)});string(parsed.keys())"
    ) == ["factor"]

    with pytest.raises(RuntimeError, match="必须是字典或标准 JSON 对象"):
        ddb_session.run("parse_definitions(1 2)")
    with pytest.raises(RuntimeError, match="值类型必须为 ANY"):
        ddb_session.run('parse_definitions(dict(["factor"], [1]))')


def test_compute_factors_handles_dependencies_empty_input_and_errors(ddb_session) -> None:
    """完整入口支持跨因子依赖和空集合，并拒绝错误 source、重名及坏 JSON。"""
    source = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
    definitions = {
        "first": direct("binary.add", {"left": "x", "right": 1}),
        "second": direct("binary.mul", {"left": "first", "right": 2}),
        "third": direct("binary.add", {"left": "first", "right": "second"}),
    }
    result = compute_factors(ddb_session, source, definitions)
    assert list(result.columns) == ["x", "first", "second", "third"]
    assert_vector_equal(result["first"], [2.0, 3.0, 4.0])
    assert_vector_equal(result["second"], [4.0, 6.0, 8.0])
    assert_vector_equal(result["third"], [6.0, 9.0, 12.0])

    ddb_session.upload({"runtime_source": source})
    empty = ddb_session.run("compute_factors(runtime_source, dict(STRING,ANY))")
    pd.testing.assert_frame_equal(empty.reset_index(drop=True), source)

    with pytest.raises(RuntimeError, match="source 必须是 table"):
        ddb_session.run("compute_factors(1 2, dict(STRING,ANY))")
    with pytest.raises(RuntimeError, match="命名因子与输入列重名：x"):
        ddb_session.run(
            f"compute_factors(runtime_source, {_ddb_json({'x': definitions['first']})})"
        )
    with pytest.raises(RuntimeError):
        ddb_session.run('compute_factors(runtime_source, "{bad json}")')


def test_complete_dsl_on_expression_filters_before_ts_and_cs(ddb_session) -> None:
    """嵌套 BOOL on 只让符合条件的行进入窗口或截面，未选中行最终回填 NULL。"""
    source = pd.DataFrame(
        {
            "time": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-03"] * 2
            ),
            "code": ["A"] * 3 + ["B"] * 3,
            "x": [1.0, -2.0, 5.0, 10.0, 20.0, -3.0],
        }
    )
    positive = direct("binary.gt", {"left": "x", "right": 0})
    definitions = {
        "positive_cumsum": time_series(
            "unary.cum_sum",
            {"col": "x"},
            {"min_periods": 1},
            on=positive,
        ),
        "positive_demean": cross_section(
            "unary.demean",
            {"col": "x"},
            on=positive,
        ),
    }
    result = compute_factors(ddb_session, source, definitions)
    assert_vector_equal(result["positive_cumsum"], [1.0, np.nan, 6.0, 10.0, 30.0, np.nan])
    assert_vector_equal(result["positive_demean"], [-4.5, np.nan, 0.0, 4.5, 0.0, np.nan])


def test_null_comparison_does_not_select_rows_for_on(ddb_session) -> None:
    """比较中的 NULL 保持未知，并由 on 规范化为 false 后排除。"""
    source = pd.DataFrame(
        {
            "time": pd.to_datetime(["2024-01-02"] * 3),
            "code": ["A", "B", "C"],
            "x": [np.nan, 5.0, 15.0],
        }
    )
    below_ten = direct("binary.lt", {"left": "x", "right": 10})
    result = compute_factors(
        ddb_session,
        source,
        {
            "below_ten": below_ten,
            "selected_mean": cross_section(
                "unary.mean",
                {"col": "x"},
                on=below_ten,
            ),
        },
    )
    assert_vector_equal(result["below_ten"], [None, True, False])
    assert_vector_equal(result["selected_mean"], [np.nan, 5.0, np.nan])
