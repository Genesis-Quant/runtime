"""生成回测框架内置工具函数的 DolphinDB 脚本。"""

from pathlib import Path

from config import DOLPHIN
from core.database.compile import build_script as compile_script
from core.database.compile import write_script as write_compiled_script
from core.database.query.scripts import write_script as write_query_script
from core.utils import logger

from .functions import BACKTEST_FUNCTIONS

MODULE = "backtest"
OUTPUT_DIR = Path(__file__).resolve().parents[3] / "output"
SCRIPT_PATH = OUTPUT_DIR / "backtest.dos"


def build_script() -> str:
    """生成 backtest.dos 模块。"""
    script = compile_script(MODULE, BACKTEST_FUNCTIONS)
    return script.replace(
        f"module {MODULE}\n\n",
        f"""module {MODULE}
loadPlugin("MatchingEngineSimulator")
loadPlugin("Backtest")
""",
        1,
    )


def write_script() -> tuple[Path, ...]:
    """按依赖顺序生成 common、query 和 backtest 模块。"""
    write_query_script()
    paths = write_compiled_script(
        MODULE,
        build_script(),
        output_dir=OUTPUT_DIR,
        module_dir=DOLPHIN.MODULE_DIR,
    )
    logger.success(
        f"DolphinDB backtest 模块已生成：{', '.join(map(str, paths))}"
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
