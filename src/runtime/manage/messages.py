"""构造或发送结构化消息的管理命令。"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from runtime.messaging import normalize_channel_name, read_message, send_message


def build_parser(*, prog: str | None = None) -> argparse.ArgumentParser:
    """创建消息发送命令。"""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="通过指定 Channel 发送结构化消息。",
        allow_abbrev=False,
    )
    commands = parser.add_subparsers(
        dest="message_command",
        metavar="COMMAND",
        required=True,
    )
    send_parser = commands.add_parser(
        "send",
        help="发送已有结构化消息 JSON",
        allow_abbrev=False,
    )
    send_parser.add_argument("--input-file", required=True, type=message_file)
    add_channel_argument(send_parser)
    send_parser.set_defaults(message_handler=send_message_file)

    return parser


def add_channel_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--channel",
        default="console",
        type=channel_name,
        help="消息发送渠道，默认 console",
    )


def channel_name(value: str) -> str:
    try:
        return normalize_channel_name(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def message_file(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"消息文件不存在：{path}")
    return path.resolve()


def send_message_file(arguments: argparse.Namespace) -> int:
    message = read_message(arguments.input_file)
    delivery = send_message(message, arguments.channel)
    print(delivery.model_dump_json())
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    prog: str | None = None,
) -> int:
    parser = build_parser(prog=prog)
    arguments = parser.parse_args(argv)
    try:
        return int(arguments.message_handler(arguments))
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
