"""生成 query DolphinDB 模块。"""

from pathlib import Path

from core.database.compile.common.scripts import (
    write_script as write_common_script,
)
from core.database.compile import (
    build_script as compile_script,
    write_script as write_compiled_script,
)
from core.utils import logger

from .functions import QUERY_FUNCTIONS

MODULE = "query"
DEFAULT_OUTPUT_DIR = Path("output")


def build_script() -> str:
    """生成 query.dos 模块。"""
    return compile_script(MODULE, QUERY_FUNCTIONS, uses=("ta",))


def write_script(*, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    """按依赖顺序生成 common.dos 和 query.dos。"""
    write_common_script(output_dir=output_dir)
    path = write_compiled_script(
        MODULE,
        build_script(),
        output_dir=output_dir,
    )
    logger.success(f"DolphinDB query 模块已生成：{path}")
    return path


if __name__ == "__main__":
    print(write_script())


__all__ = [
    "MODULE",
    "DEFAULT_OUTPUT_DIR",
    "build_script",
    "write_script",
]
