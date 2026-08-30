"""注册并分发 Runtime 应用命令。"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any, Final

from . import backtest, factor, optimization, query, sensitivity

APPLICATIONS: Final[tuple[ModuleType, ...]] = (
    query,
    factor,
    backtest,
    optimization,
    sensitivity,
)


def load_input_file(
    parser: argparse.ArgumentParser,
    path: Path,
) -> dict[str, Any]:
    """读取 UTF-8 JSON 对象，格式错误时按命令行参数错误退出。"""
    try:
        content = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        parser.error(f"无法读取输入文件 {path}：{error}")
    try:
        result = json.loads(content)
    except json.JSONDecodeError as error:
        parser.error(
            f"输入文件 {path} 不是有效 JSON："
            f"第 {error.lineno} 行第 {error.colno} 列，{error.msg}"
        )
    if not isinstance(result, dict):
        parser.error(f"输入文件 {path} 的顶层必须是 JSON 对象")
    return result


def build_parser(*, prog: str | None = None) -> argparse.ArgumentParser:
    """创建应用命令解析器并显式注册每个应用。"""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="运行查询、因子分析、回测、参数调优或敏感性分析应用。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  core-manage apps query --input-file query.json --output-dir output/query --output data --cloud false\n"
            "  core-manage apps factor --input-file factor.json --output-dir output/factor --output processed_data information_coefficient --cloud false\n"
            "  core-manage apps backtest --input-file backtest.json --output-dir output/backtest --output trade_details daily_positions daily_portfolios daily_trading_statistics --cloud false\n"
            "  core-manage apps optimization --input-file optimization.json --output-dir output/optimization --cloud false\n"
            "  core-manage apps sensitivity --input-file sensitivity.json --output-dir output/sensitivity --cloud false"
        ),
    )
    commands = parser.add_subparsers(
        dest="app",
        metavar="APP",
        required=True,
    )
    for application in APPLICATIONS:
        application_parser = commands.add_parser(
            application.NAME,
            help=application.HELP,
            description=application.DESCRIPTION,
            allow_abbrev=False,
        )
        application.configure_parser(application_parser)
        application_parser.set_defaults(
            application_handler=application.run
        )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    prog: str | None = None,
) -> int:
    """解析参数并运行选中的应用命令。"""
    parser = build_parser(prog=prog)
    arguments = parser.parse_args(argv)
    data = load_input_file(parser, arguments.input_file)
    handler: Any = arguments.application_handler
    return int(handler(parser, arguments, data))


__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
