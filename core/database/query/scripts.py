"""生成 query DolphinDB 模块。"""

from pathlib import Path

from config import DOLPHIN
from core.database.common.scripts import write_script as write_common_script
from core.database.compile import (
    build_script as compile_script,
    write_script as write_compiled_script,
)
from core.utils import logger

from .functions import QUERY_FUNCTIONS

MODULE = "query"
OUTPUT_DIR = Path(__file__).resolve().parents[3] / "output"
SCRIPT_PATH = OUTPUT_DIR / "query.dos"


def build_script() -> str:
    """生成 query.dos 模块。"""
    return compile_script(MODULE, QUERY_FUNCTIONS, uses=("ta",))


def write_script() -> tuple[Path, ...]:
    """按依赖顺序生成 common.dos 和 query.dos。"""
    write_common_script()
    paths = write_compiled_script(
        MODULE,
        build_script(),
        output_dir=OUTPUT_DIR,
        module_dir=DOLPHIN.MODULE_DIR,
    )
    logger.success(
        f"DolphinDB query 模块已生成：{', '.join(map(str, paths))}"
    )
    return paths


if __name__ == "__main__":
    print(*write_script(), sep="\n")


__all__ = [
    "MODULE",
    "OUTPUT_DIR",
    "SCRIPT_PATH",
    "build_script",
    "write_script",
]
