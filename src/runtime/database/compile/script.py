"""构建并写入 DolphinDB 模块。"""

from collections.abc import Iterable
from pathlib import Path

from .function import DolphinDBFunction
from .utils import collect_functions, collect_used_modules, render_functions


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
