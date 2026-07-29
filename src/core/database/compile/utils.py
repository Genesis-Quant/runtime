"""提供 DolphinDB 函数依赖收集和源码渲染能力。"""

from collections.abc import Iterable

from .function import DolphinDBFunction


def collect_functions(
    functions: Iterable[DolphinDBFunction],
    module: str | None = None,
) -> tuple[DolphinDBFunction, ...]:
    """按依赖顺序收集同一模块的函数，不内联跨模块依赖。"""
    roots = tuple(functions)
    if module is None and roots:
        root_modules = {function.module for function in roots}
        if len(root_modules) != 1:
            raise ValueError(
                f"DolphinDB 根函数必须属于同一模块：{sorted(map(str, root_modules))}"
            )
        module = roots[0].module

    ordered: list[DolphinDBFunction] = []
    definitions: dict[str, DolphinDBFunction] = {}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(function: DolphinDBFunction) -> None:
        """递归登记当前函数及其直接依赖。"""
        if function.module != module:
            return
        existing = definitions.get(function.name)
        if existing is not None and existing != function:
            raise ValueError(
                f"DolphinDB 模块 {module!r} 中函数 {function.name!r} 重复定义"
            )
        definitions[function.name] = function
        if function.name in visited:
            return
        if function.name in visiting:
            raise ValueError(f"DolphinDB 函数依赖存在循环：{function.name}")

        visiting.add(function.name)
        for dependency in function.dependencies:
            visit(dependency)
        visiting.remove(function.name)
        visited.add(function.name)
        ordered.append(function)

    for function in roots:
        if function.module != module:
            raise ValueError(
                f"DolphinDB 根函数 {function.name!r} 属于模块 "
                f"{function.module!r}，不是 {module!r}"
            )
        visit(function)
    return tuple(ordered)


def collect_used_modules(
    functions: Iterable[DolphinDBFunction],
    module: str,
) -> tuple[str, ...]:
    """收集当前模块函数直接引用的其他 DolphinDB 模块。"""
    used: set[str] = set()
    visited: set[tuple[str | None, str]] = set()

    def visit(function: DolphinDBFunction) -> None:
        key = (function.module, function.name)
        if key in visited:
            return
        visited.add(key)
        for dependency in function.dependencies:
            if dependency.module is None:
                raise ValueError(
                    f"DolphinDB 函数 {function.name!r} 依赖的 "
                    f"{dependency.name!r} 未声明 module"
                )
            if dependency.module == module:
                visit(dependency)
            else:
                used.add(dependency.module)

    for function in functions:
        if function.module != module:
            raise ValueError(
                f"DolphinDB 根函数 {function.name!r} 属于模块 "
                f"{function.module!r}，不是 {module!r}"
            )
        visit(function)
    return tuple(sorted(used))


def render_functions(functions: Iterable[DolphinDBFunction]) -> str:
    """按输入顺序连接完整函数定义。"""
    definitions = "\n\n".join(function.definition for function in functions)
    return f"{definitions}\n" if definitions else ""
