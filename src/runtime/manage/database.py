"""实现 DolphinDB 代码管理命令。"""

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import dolphindb

from runtime.config import DolphinSettings
from runtime.database.session import configured_dolphin_endpoints
from runtime.utils import logger


def regenerate_dos(output_dir: Path | str = "output") -> tuple[Path, ...]:
    """按依赖顺序重新生成全部 DolphinDB DOS 模块。"""
    from runtime.database.compile import write_script
    from runtime.database.compile.backtest.scripts import build_script as build_backtest
    from runtime.database.compile.common.scripts import build_script as build_common
    from runtime.database.compile.factor.scripts import build_script as build_factor
    from runtime.database.compile.query.scripts import build_script as build_query

    target = Path(output_dir).expanduser().resolve()
    modules = (
        ("common", build_common),
        ("query", build_query),
        ("factor", build_factor),
        ("backtest", build_backtest),
    )
    paths = tuple(
        write_script(module, build(), output_dir=target)
        for module, build in modules
    )
    return paths


def upload_dos(session: Any, path: Path) -> None:
    """把一个编译后的 DOS 模块写入并校验当前节点的 moduleDir。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != f"module {path.stem}":
        raise ValueError(f"DolphinDB 模块声明与文件名不一致：{path}")
    session.upload({
        "arenaModuleFileName": path.name,
        "arenaModuleLines": lines,
    })
    verified = session.run("""
        arenaModulePath = getHomeDir() + "/" + getConfig(`moduleDir) + "/" + arenaModuleFileName
        arenaModuleFile = file(arenaModulePath, "w")
        arenaModuleFile.writeLines(arenaModuleLines)
        arenaModuleFile.close()
        arenaModuleFile = file(arenaModulePath)
        arenaUploadedLines = arenaModuleFile.readLines(size(arenaModuleLines) + 1)
        arenaModuleFile.close()
        size(arenaUploadedLines) == size(arenaModuleLines) && all(arenaUploadedLines == arenaModuleLines)
    """)
    if not verified:
        raise RuntimeError(f"DolphinDB 模块上传后内容校验失败：{path.name}")


def upload_dos_modules(paths: Sequence[Path]) -> tuple[str, ...]:
    """把编译后的模块部署到全部配置节点并验证可以导入。"""
    username, password = DolphinSettings.credentials("worker")
    modules = tuple(Path(path).resolve() for path in paths)
    aliases: list[str] = []
    for host, port in configured_dolphin_endpoints():
        session = dolphindb.session(show_output=False)
        try:
            if not session.connect(host, port, username, password):
                raise ConnectionError(f"无法连接 DolphinDB 节点：{host}:{port}")
            alias = str(session.run("getNodeAlias()"))
            logger.info(f"部署 DolphinDB DOS 模块：{alias} ({host}:{port})")
            for path in modules:
                upload_dos(session, path)
            session.run("\n".join(f"use {path.stem}" for path in modules))
            aliases.append(alias)
        finally:
            session.close()
    return tuple(aliases)


def build_parser(*, prog: str | None = None) -> argparse.ArgumentParser:
    """创建数据库管理命令解析器。"""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="管理 DolphinDB 代码。",
        epilog=(
            "示例：\n"
            "  core-manage database compile\n"
            "  core-manage database compile --upload\n"
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
    compile_parser.add_argument(
        "--upload",
        action="store_true",
        help="编译后上传到全部 DolphinDB 数据和计算节点并校验",
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
    if arguments.upload:
        aliases = upload_dos_modules(paths)
        print(f"DolphinDB DOS 模块已部署到 {len(aliases)} 个节点：{', '.join(aliases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
