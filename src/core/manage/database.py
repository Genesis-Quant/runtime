"""实现 DolphinDB 代码管理命令。"""

import argparse
from collections.abc import Sequence
from pathlib import Path


DOS_NAMES = ("common.dos", "query.dos", "factor.dos", "backtest.dos")


def regenerate_dos(output_dir: Path | str = "output") -> tuple[Path, ...]:
    """按依赖顺序重新生成全部 DolphinDB DOS 模块。"""
    from core.database.compile.backtest.scripts import (
        write_script as write_backtest_script,
    )
    from core.database.compile.factor.scripts import (
        write_script as write_factor_script,
    )

    target = Path(output_dir).expanduser().resolve()
    write_backtest_script(output_dir=target)
    write_factor_script(output_dir=target)
    paths = tuple(target / name for name in DOS_NAMES)
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(
            "DOS 模块生成后缺少文件："
            + "、".join(map(str, missing))
        )
    return paths


def build_parser(*, prog: str | None = None) -> argparse.ArgumentParser:
    """创建数据库管理命令解析器。"""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="管理 DolphinDB 代码。",
        epilog=(
            "示例：\n"
            "  core-manage database compile\n"
            "  python manage.py database compile --output-dir output"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(
        metavar="COMMAND",
        required=True,
    )
    compile_parser = commands.add_parser(
        "compile",
        help="重新生成 common、query、factor 和 backtest DOS 模块",
        description=(
            "重新生成 common、query、factor 和 backtest DolphinDB DOS 模块。"
        ),
        allow_abbrev=False,
    )
    compile_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        metavar="DIR",
        help="DOS 输出目录，默认是当前工作目录下的 output",
    )
    return parser


def main(
        argv: Sequence[str] | None = None,
        *,
        prog: str | None = None,
) -> int:
    """解析数据库管理命令。"""
    parser = build_parser(prog=prog)
    arguments = parser.parse_args(argv)
    paths = regenerate_dos(arguments.output_dir)
    print("DolphinDB DOS 模块已全部重新生成：")
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
