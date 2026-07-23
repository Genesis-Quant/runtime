"""定义可组合的 DolphinDB 函数源码。"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from textwrap import dedent
from typing import Iterable

_FUNCTION_PATTERN = re.compile(
    r"^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*\{",
    re.MULTILINE,
)
_PARAMETER_PATTERN = re.compile(
    r"(?:mutable\s+)?([A-Za-z_][A-Za-z0-9_]*)"
)


@dataclass(frozen=True, slots=True)
class DolphinDBFunction:
    """保存一个 DolphinDB 函数及其直接依赖。"""

    definition: str
    dependencies: tuple[DolphinDBFunction, ...] = ()
    name: str = field(init=False)
    parameters: tuple[str, ...] = field(init=False)
    signature: str = field(init=False)

    def __post_init__(self) -> None:
        """从函数定义解析并校验名称和参数。"""
        definition = dedent(self.definition).strip()
        match = _FUNCTION_PATTERN.match(definition)
        if match is None:
            raise ValueError("definition 必须以完整的 DolphinDB def 函数定义开头")

        raw_parameters = tuple(
            parameter.strip() for parameter in match.group(2).split(",") if parameter.strip()
        )
        parameter_matches = [
            _PARAMETER_PATTERN.fullmatch(parameter)
            for parameter in raw_parameters
        ]
        invalid = [
            parameter
            for parameter, parameter_match in zip(
                raw_parameters,
                parameter_matches,
                strict=True,
            )
            if parameter_match is None
        ]
        if invalid:
            raise ValueError(f"DolphinDB 函数参数名非法：{invalid}")
        parameters = tuple(
            parameter_match.group(1)
            for parameter_match in parameter_matches
            if parameter_match is not None
        )
        if len(parameters) != len(set(parameters)):
            raise ValueError(f"DolphinDB 函数 {match.group(1)!r} 包含重复参数")

        dependency_names = [dependency.name for dependency in self.dependencies]
        if len(dependency_names) != len(set(dependency_names)):
            raise ValueError(f"DolphinDB 函数 {match.group(1)!r} 包含重复依赖")

        object.__setattr__(self, "definition", definition)
        object.__setattr__(self, "name", match.group(1))
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(self, "signature", match.group(2).strip())


def collect_functions(functions: Iterable[DolphinDBFunction]) -> tuple[DolphinDBFunction, ...]:
    """按依赖顺序收集函数，同名函数只保留一份。"""
    ordered: list[DolphinDBFunction] = []
    definitions: dict[str, DolphinDBFunction] = {}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(function: DolphinDBFunction) -> None:
        """递归登记当前函数及其直接依赖。"""
        existing = definitions.get(function.name)
        if existing is not None and existing != function:
            raise ValueError(f"DolphinDB 函数 {function.name!r} 重复定义")
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

    for f in functions:
        visit(f)
    return tuple(ordered)


def render_functions(functions: Iterable[DolphinDBFunction]) -> str:
    """按输入顺序连接完整函数定义。"""
    definitions = "\n\n".join(function.definition for function in functions)
    return f"{definitions}\n" if definitions else ""


__all__ = ["DolphinDBFunction", "collect_functions", "render_functions"]
