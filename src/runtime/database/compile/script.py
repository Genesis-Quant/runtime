"""构建并写入 DolphinDB 模块。"""

from collections.abc import Callable, Iterable
from pathlib import Path

from runtime.utils import logger

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

    def visit(current: DolphinDBFunction) -> None:
        if current.module != module:
            return
        existing = definitions.get(current.name)
        if existing is not None and existing != current:
            raise ValueError(
                f"DolphinDB 模块 {module!r} 中函数 {current.name!r} 重复定义"
            )
        definitions[current.name] = current
        if current.name in visited:
            return
        if current.name in visiting:
            raise ValueError(f"DolphinDB 函数依赖存在循环：{current.name}")

        visiting.add(current.name)
        for dependency in current.dependencies:
            visit(dependency)
        visiting.remove(current.name)
        visited.add(current.name)
        ordered.append(current)

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

    def visit(current: DolphinDBFunction) -> None:
        key = (current.module, current.name)
        if key in visited:
            return
        visited.add(key)
        for dependency in current.dependencies:
            if dependency.module is None:
                raise ValueError(
                    f"DolphinDB 函数 {current.name!r} 依赖的 "
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


def build_script(
    module: str,
    functions: Iterable[DolphinDBFunction],
    *,
    uses: Iterable[str] = (),
) -> str:
    """生成包含 module、自动 use 和函数定义的完整 DOS 模块。"""
    roots = tuple(functions)
    compiled = collect_functions(roots, module)
    imported = set(uses)
    imported.update(collect_used_modules(roots, module))
    imported.discard(module)

    statements = [f"module {module}"]
    statements.extend(f"use {name}" for name in sorted(imported))
    definitions = render_functions(compiled).rstrip()
    if definitions:
        statements.append(definitions)
    return "\n\n".join(statements).rstrip() + "\n"


def write_script(
    module: str,
    script: str,
    *,
    output_dir: Path,
) -> Path:
    """将模块写入项目输出目录。"""
    relative_path = Path(*module.split("::")).with_suffix(".dos")
    path = output_dir / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != script:
        path.write_text(script, encoding="utf-8", newline="\n")
    return path


def write_module(
        module: str,
        script: str,
        *,
        output_dir: Path,
        dependencies: Iterable[Callable[..., Path]] = (),
) -> Path:
    """先生成依赖模块，再写入当前模块并记录结果。"""
    for dependency in dependencies:
        dependency(output_dir=output_dir)
    path = write_script(module, script, output_dir=output_dir)
    logger.success(f"DolphinDB {module} 模块已生成：{path}")
    return path
