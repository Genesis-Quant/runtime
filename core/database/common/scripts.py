"""生成 common DolphinDB 模块。"""

from pathlib import Path

from config import DOLPHIN
from core.database.compile import (
    build_script as compile_script,
    write_script as write_compiled_script,
)
from core.utils import logger

from .functions import COMMON_FUNCTIONS

MODULE = "common"
OUTPUT_DIR = Path(__file__).resolve().parents[3] / "output"


def build_script() -> str:
    """生成 common.dos。"""
    return compile_script(MODULE, COMMON_FUNCTIONS)


def write_script() -> tuple[Path, ...]:
    """将 common.dos 写入项目输出和 DolphinDB modules 目录。"""
    paths = write_compiled_script(
        MODULE,
        build_script(),
        output_dir=OUTPUT_DIR,
        module_dir=DOLPHIN.MODULE_DIR,
    )
    logger.success(
        f"DolphinDB common 模块已生成：{', '.join(map(str, paths))}"
    )
    return paths


if __name__ == "__main__":
    print(*write_script(), sep="\n")


__all__ = [
    "MODULE",
    "OUTPUT_DIR",
    "build_script",
    "write_script",
]
