"""生成 query DolphinDB 模块。"""

from pathlib import Path

from runtime.database.compile import (
    build_script as compile_script,
)
from runtime.database.compile.common.scripts import (
    write_script as write_common_script,
)
from runtime.database.compile.script import write_module

from .functions import QUERY_FUNCTIONS

MODULE = "query"
DEFAULT_OUTPUT_DIR = Path("output")


def build_script() -> str:
    """生成 query.dos 模块。"""
    return compile_script(MODULE, QUERY_FUNCTIONS, uses=("ta",))


def write_script(*, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    """按依赖顺序生成 common.dos 和 query.dos。"""
    return write_module(
        MODULE,
        build_script(),
        output_dir=output_dir,
        dependencies=(write_common_script,),
    )


if __name__ == "__main__":
    print(write_script())
