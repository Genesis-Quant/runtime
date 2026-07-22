"""测试 DolphinDB 函数对象、依赖拓扑和完整脚本生成逻辑。"""

from pathlib import Path
import runpy
from typing import get_args

import pytest

from core.query.dolphindb.function import (
    DolphinDBFunction,
    collect_functions,
    render_functions,
)
from core.query.dolphindb.script import (
    SCRIPT_PATH,
    build_script,
    evaluator_functions,
    write_script,
)
from core.query.operator import Derivative


def test_function_parses_and_normalizes_definition() -> None:
    """函数定义应去除公共缩进并解析普通、mutable 和空参数。"""
    function = DolphinDBFunction(
        """
        def sample(first, mutable cache) {
            return first
        }
        """
    )
    assert function.name == "sample"
    assert function.parameters == ("first", "cache")
    assert function.signature == "first, mutable cache"
    assert function.definition.startswith("def sample")

    empty = DolphinDBFunction("def empty() { return 1 }")
    assert empty.parameters == ()
    assert empty.signature == ""


@pytest.mark.parametrize(
    ("definition", "message"),
    [
        ("return 1", "必须以完整的 DolphinDB def"),
        ("def bad(a-b) { return 1 }", "参数名非法"),
        ("def duplicate(value, value) { return value }", "包含重复参数"),
    ],
)
def test_function_rejects_invalid_definitions(
    definition: str,
    message: str,
) -> None:
    """不完整定义、非法参数和重复参数必须在 Python 端失败。"""
    with pytest.raises(ValueError, match=message):
        DolphinDBFunction(definition)


def test_function_rejects_duplicate_direct_dependencies() -> None:
    """同一函数不能在 dependencies 中重复列出同名依赖。"""
    dependency = DolphinDBFunction("def dependency() { return 1 }")
    with pytest.raises(ValueError, match="包含重复依赖"):
        DolphinDBFunction(
            "def parent() { return dependency() }",
            dependencies=(dependency, dependency),
        )


def test_collect_functions_orders_dependencies_and_deduplicates() -> None:
    """依赖必须位于调用者之前，多条路径引用同一对象时只输出一次。"""
    leaf = DolphinDBFunction("def leaf() { return 1 }")
    left = DolphinDBFunction(
        "def left() { return leaf() }",
        dependencies=(leaf,),
    )
    right = DolphinDBFunction(
        "def right() { return leaf() }",
        dependencies=(leaf,),
    )
    root = DolphinDBFunction(
        "def root() { return left() + right() }",
        dependencies=(left, right),
    )
    assert [item.name for item in collect_functions((root, leaf))] == [
        "leaf",
        "left",
        "right",
        "root",
    ]


def test_collect_functions_rejects_conflicts_and_cycles() -> None:
    """同名异义函数和循环依赖都必须拒绝。"""
    first = DolphinDBFunction("def same() { return 1 }")
    second = DolphinDBFunction("def same() { return 2 }")
    with pytest.raises(ValueError, match="重复定义"):
        collect_functions((first, second))

    left = DolphinDBFunction("def cycle_left() { return cycle_right() }")
    right = DolphinDBFunction(
        "def cycle_right() { return cycle_left() }",
        dependencies=(left,),
    )
    object.__setattr__(left, "dependencies", (right,))
    with pytest.raises(ValueError, match="依赖存在循环"):
        collect_functions((left,))


def test_render_functions_handles_empty_and_non_empty_inputs() -> None:
    """渲染器应保留输入顺序，并只在非空结果末尾添加换行。"""
    first = DolphinDBFunction("def first() { return 1 }")
    second = DolphinDBFunction("def second() { return 2 }")
    assert render_functions(()) == ""
    assert render_functions((first, second)) == (
        "def first() { return 1 }\n\ndef second() { return 2 }\n"
    )


def test_generated_evaluators_cover_all_registered_operators() -> None:
    """三类 evaluator 必须各自包含且只包含对应的已登记算符。"""
    direct, time_series, cross_section = evaluator_functions()
    definitions = {
        "DIRECT": direct.definition,
        "TS": time_series.definition,
        "CS": cross_section.definition,
    }
    for operation, model in Derivative.operators.items():
        marker = f'if (op == "{operation}")'
        node_type = get_args(model.model_fields["type"].annotation)[0]
        assert definitions[node_type].count(marker) == 1
        for other_type, definition in definitions.items():
            if other_type != node_type:
                assert marker not in definition

    assert "apply_controlled_cross_section" in cross_section.definition
    assert "apply_grouped_cross_section" in cross_section.definition
    assert "apply_cross_section" in cross_section.definition
    assert 'double(params["span"])' in time_series.definition
    assert 'int(params["min_periods"])' in time_series.definition


def test_build_script_has_stable_sections_and_unique_definitions() -> None:
    """完整脚本应按工具、DIRECT、TS、CS、derive 排列且函数名不重复。"""
    script = build_script()
    markers = [
        "// 工具函数",
        "// DIRECT operators",
        "// TS operators",
        "// CS operators",
        "// derive",
    ]
    positions = [script.index(marker) for marker in markers]
    assert positions == sorted(positions)
    assert script.startswith("use ta\n")
    assert script.endswith("\n")
    assert "def compute_factors(" in script

    names = [line.split("(", 1)[0].removeprefix("def ") for line in script.splitlines() if line.startswith("def ")]
    assert len(names) == len(set(names))
    for model in Derivative.operators.values():
        assert names.count(model.function.name) == 1


def test_write_script_supports_custom_and_default_paths(tmp_path: Path) -> None:
    """脚本可以写入自定义路径，默认路径也必须与生成结果同步。"""
    custom = tmp_path / "nested" / "operators.dos"
    assert write_script(custom) == custom
    assert custom.read_text(encoding="utf-8") == build_script()

    assert write_script() == SCRIPT_PATH
    assert SCRIPT_PATH.read_text(encoding="utf-8") == build_script()


def test_script_module_entry_point_writes_and_prints_path(capsys) -> None:
    """直接运行生成模块时应执行写入入口并输出目标路径。"""
    with pytest.warns(RuntimeWarning, match="found in sys.modules"):
        runpy.run_module("core.query.dolphindb.script", run_name="__main__")
    assert str(SCRIPT_PATH) in capsys.readouterr().out
