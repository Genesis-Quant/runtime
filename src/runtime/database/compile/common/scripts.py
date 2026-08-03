"""生成 common DolphinDB 模块。"""

from pathlib import Path

from runtime.database.compile import (
    build_script as compile_script,
    write_script as write_compiled_script,
)
from runtime.utils import logger

from .functions import COMMON_FUNCTIONS

MODULE = "common"
DEFAULT_OUTPUT_DIR = Path("output")


def build_script() -> str:
    """生成 common.dos。"""
    return compile_script(MODULE, COMMON_FUNCTIONS)


def write_script(*, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    """将 common.dos 写入指定输出目录。"""
    path = write_compiled_script(
        MODULE,
        build_script(),
        output_dir=output_dir,
    )
    logger.success(f"DolphinDB common 模块已生成：{path}")
    return path


if __name__ == "__main__":
    print(write_script())
