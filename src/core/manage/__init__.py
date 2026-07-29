"""注册并分发 Core 管理命令。"""

import argparse
from collections.abc import Sequence
from importlib import import_module
from typing import Final


COMMANDS: Final[dict[str, tuple[str, str]]] = {
    "apps": (
        "运行查询或回测应用",
        "core.manage.apps",
    ),
    "workers": (
        "运行数据写入 Worker",
        "core.manage.workers",
    ),
    "database": (
        "管理 DolphinDB 代码",
        "core.manage.database",
    ),
}


def build_parser(*, prog: str | None = None) -> argparse.ArgumentParser:
    """创建只负责一级命令选择的根解析器。"""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Core 管理命令。",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(
        dest="command",
        metavar="COMMAND",
        required=True,
    )
    for name, (description, module_name) in COMMANDS.items():
        command_parser = subparsers.add_parser(
            name,
            help=description,
            description=description,
            add_help=False,
            allow_abbrev=False,
        )
        command_parser.set_defaults(command_module=module_name)
    return parser


def main(
        argv: Sequence[str] | None = None,
        *,
        prog: str | None = None,
) -> int:
    """解析一级命令，并把剩余参数交给对应管理模块。"""
    parser = build_parser(prog=prog)
    arguments, remaining = parser.parse_known_args(argv)
    module = import_module(arguments.command_module)
    command_main = getattr(module, "main")
    return int(
        command_main(
            remaining,
            prog=f"{parser.prog} {arguments.command}",
        )
    )


__all__ = ["main"]
