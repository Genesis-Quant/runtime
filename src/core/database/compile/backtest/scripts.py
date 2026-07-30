"""生成回测框架内置工具函数的 DolphinDB 脚本。"""

from pathlib import Path

from core.database.compile import build_script as compile_script
from core.database.compile import write_script as write_compiled_script
from core.database.compile.query.scripts import write_script as write_query_script
from core.utils import logger

from .functions import BACKTEST_FUNCTIONS

MODULE = "backtest"
DEFAULT_OUTPUT_DIR = Path("output")


def build_script() -> str:
    """生成 backtest.dos 模块。"""
    return compile_script(MODULE, BACKTEST_FUNCTIONS)

def write_script(*, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    """按依赖顺序生成 common、query 和 backtest 模块。"""
    write_query_script(output_dir=output_dir)
    path = write_compiled_script(
        MODULE,
        build_script(),
        output_dir=output_dir,
    )
    logger.success(f"DolphinDB backtest 模块已生成：{path}")
    return path


if __name__ == "__main__":
    print(write_script())
