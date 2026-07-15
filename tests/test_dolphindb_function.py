"""验证 DolphinDB 函数定义及依赖组合。"""

from collections.abc import Callable

import pytest

from core.dolphindb.function import (
    DolphinDBFunction,
    collect_functions,
    render_functions,
)


def _function(
    name: str,
    signature: str = "",
    expression: str = "true",
    dependencies: tuple[DolphinDBFunction, ...] = (),
) -> DolphinDBFunction:
    """构造用于测试的最小 DolphinDB 函数。"""
    return DolphinDBFunction(
        f"def {name}({signature}) {{\n    return {expression}\n}}",
        dependencies=dependencies,
    )


VALID_DEFINITIONS = (
    ("def zero() { return 0 }", "zero", (), ""),
    ("def identity(value) { return value }", "identity", ("value",), "value"),
    ("def mutate(mutable value) { return value }", "mutate", ("value",), "mutable value"),
    ("def pair(left, right) { return left + right }", "pair", ("left", "right"), "left, right"),
    ("def mixed(mutable cache, key) { return cache[key] }", "mixed", ("cache", "key"), "mutable cache, key"),
    ("def name_2(value_1) { return value_1 }", "name_2", ("value_1",), "value_1"),
    ("\n    def indented(x) {\n        return x * 2\n    }\n", "indented", ("x",), "x"),
    ("def spaced( left , mutable right ) { return left }", "spaced", ("left", "right"), "left , mutable right"),
    ("def multiline(\n left,\n mutable right\n) { return left }", "multiline", ("left", "right"), "left,\n mutable right"),
    ("def body(value) {\n    result = value + 1\n    return result\n}", "body", ("value",), "value"),
)


@pytest.mark.parametrize(
    ("definition", "name", "parameters", "signature"),
    VALID_DEFINITIONS,
)
def test_dolphindb_function_parses_definition(
    definition: str,
    name: str,
    parameters: tuple[str, ...],
    signature: str,
) -> None:
    """完整函数定义应解析出可调用签名。"""
    function = DolphinDBFunction(definition)

    assert function.name == name
    assert function.parameters == parameters
    assert function.signature == signature
    assert function.definition.startswith(f"def {name}(")


INVALID_BUILDERS: tuple[Callable[[], DolphinDBFunction], ...] = (
    lambda: DolphinDBFunction(""),
    lambda: DolphinDBFunction("zero() { return 0 }"),
    lambda: DolphinDBFunction("function zero() { return 0 }"),
    lambda: DolphinDBFunction("def 2zero() { return 0 }"),
    lambda: DolphinDBFunction("def missing() return 0"),
    lambda: DolphinDBFunction("def bad-name(value) { return value }"),
    lambda: DolphinDBFunction("def bad(value-name) { return value }"),
    lambda: DolphinDBFunction("def bad(INT value) { return value }"),
    lambda: DolphinDBFunction("def duplicate(value, value) { return value }"),
    lambda: DolphinDBFunction(
        "def duplicate_dependency() { return true }",
        dependencies=(_function("dependency"), _function("dependency")),
    ),
)


@pytest.mark.parametrize("builder", INVALID_BUILDERS)
def test_dolphindb_function_rejects_invalid_definition(
    builder: Callable[[], DolphinDBFunction],
) -> None:
    """非法函数定义和重复依赖应在构造时失败。"""
    with pytest.raises(ValueError):
        builder()


def _dependency_cases() -> tuple[
    tuple[tuple[DolphinDBFunction, ...], tuple[str, ...]], ...
]:
    """构造十种有向无环依赖关系。"""
    a = _function("a")
    b = _function("b")
    c = _function("c", dependencies=(a,))
    d = _function("d", dependencies=(b, c))
    e = _function("e", dependencies=(c,))
    f = _function("f", dependencies=(d, e))
    g = _function("g", dependencies=(a, b))
    h = _function("h", dependencies=(g,))
    equivalent_a = _function("a")
    return (
        ((), ()),
        ((a,), ("a",)),
        ((a, b), ("a", "b")),
        ((c,), ("a", "c")),
        ((d,), ("b", "a", "c", "d")),
        ((e, d), ("a", "c", "e", "b", "d")),
        ((f,), ("b", "a", "c", "d", "e", "f")),
        ((h,), ("a", "b", "g", "h")),
        ((a, a, equivalent_a), ("a",)),
        ((f, h), ("b", "a", "c", "d", "e", "f", "g", "h")),
    )


@pytest.mark.parametrize(("roots", "expected_names"), _dependency_cases())
def test_collect_functions_orders_dependencies(
    roots: tuple[DolphinDBFunction, ...],
    expected_names: tuple[str, ...],
) -> None:
    """依赖必须先于调用者且同一函数只收集一次。"""
    assert tuple(function.name for function in collect_functions(roots)) == expected_names


def _invalid_dependency_graph(index: int) -> tuple[DolphinDBFunction, ...]:
    """构造重名定义或循环依赖。"""
    if index < 5:
        first = _function(f"duplicate_{index}", expression="true")
        second = _function(f"duplicate_{index}", expression="false")
        return first, second

    first = _function(f"cycle_first_{index}")
    second = _function(f"cycle_second_{index}", dependencies=(first,))
    object.__setattr__(first, "dependencies", (second,))
    return (first,)


@pytest.mark.parametrize("index", range(10))
def test_collect_functions_rejects_invalid_graph(index: int) -> None:
    """同名不同定义和循环依赖均不能生成脚本。"""
    with pytest.raises(ValueError):
        collect_functions(_invalid_dependency_graph(index))


@pytest.mark.parametrize(
    "roots",
    tuple(roots for roots, _ in _dependency_cases()),
)
def test_render_functions_emits_input_order(
    roots: tuple[DolphinDBFunction, ...],
) -> None:
    """渲染结果只按输入顺序包含完整定义。"""
    definitions = "\n\n".join(function.definition for function in roots)
    expected = f"{definitions}\n" if definitions else ""

    rendered = render_functions(roots)

    assert rendered == expected
