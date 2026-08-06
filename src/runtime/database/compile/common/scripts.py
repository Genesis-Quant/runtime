"""生成 common DolphinDB 模块。"""

from pathlib import Path

from runtime.database.compile import (
    build_script as compile_script,
)
from runtime.database.compile.script import write_module

from .functions import COMMON_FUNCTIONS

MODULE = "common"
DEFAULT_OUTPUT_DIR = Path("output")


def build_script() -> str:
    """生成 common.dos。"""
    return compile_script(MODULE, COMMON_FUNCTIONS)


def write_script(*, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    """将 common.dos 写入指定输出目录。"""
    return write_module(MODULE, build_script(), output_dir=output_dir)


if __name__ == "__main__":
    print(write_script())
