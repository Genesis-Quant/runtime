"""注册并分发 query、factor 和 backtest 应用命令。"""

import argparse
from collections.abc import Sequence
from types import ModuleType
from typing import Any, Final

from . import backtest, factor, query
from .utils import load_input_file

APPLICATIONS: Final[tuple[ModuleType, ...]] = (
    query,
    factor,
    backtest,
)


def build_parser(*, prog: str | None = None) -> argparse.ArgumentParser:
    """创建应用命令解析器并显式注册每个应用。"""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="运行查询、因子分析或回测应用。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  core-manage apps query --input-file query.json --output-dir output/query --output data --cloud false\n"
            "  core-manage apps factor --input-file factor.json --output-dir output/factor --output processed_data information_coefficient --cloud false\n"
            "  core-manage apps backtest --input-file backtest.json --output-dir output/backtest --output daily_portfolios return_summary --cloud false"
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


__all__ = ["APPLICATIONS", "build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
