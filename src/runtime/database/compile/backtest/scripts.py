"""生成回测框架内置工具函数的 DolphinDB 脚本。"""

from pathlib import Path

from runtime.database.compile import build_script as compile_script
from runtime.database.compile.factor.scripts import write_script as write_factor_script
from runtime.database.compile.script import write_module

from .functions import BACKTEST_FUNCTIONS

MODULE = "backtest"
DEFAULT_OUTPUT_DIR = Path("output")


def build_script() -> str:
    """生成 backtest.dos 模块。"""
    return compile_script(MODULE, BACKTEST_FUNCTIONS, uses=("factor",))


def write_script(*, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    """按依赖顺序生成 common、query、factor、backtest 模块。"""
    return write_module(
        MODULE,
        build_script(),
        output_dir=output_dir,
        dependencies=(write_factor_script,),
    )


if __name__ == "__main__":
    print(write_script())
