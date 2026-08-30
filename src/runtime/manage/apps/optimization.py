"""实现滚动回测参数调优命令。"""

import argparse
from contextlib import ExitStack
from typing import Any

from runtime.config import ArenaSettings
from runtime.utils.manage import (
    boolean_argument,
    input_file_path,
    model_input,
    prepare_output_target,
    write_parquet,
)

NAME = "optimization"
HELP = "执行滚动回测参数调优"
DESCRIPTION = "复用一次完整区间查询，滚动执行样本内调优和样本外回测。"


def configure_parser(parser: argparse.ArgumentParser) -> None:
    """注册滚动参数调优命令参数。"""
    parser.add_argument(
        "--input-file",
        type=input_file_path,
        required=True,
        metavar="PATH",
        help="包含全部参数调优请求的 UTF-8 JSON 文件",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        metavar="DIR",
        help="本地输出目录或 bucket 内的相对对象路径",
    )
    parser.add_argument(
        "--cloud",
        type=boolean_argument,
        default=ArenaSettings.SHARED_CLOUD,
        help=(
            "是否将结果上传到对象存储；直接运行时默认读取 "
            "ARENA_SHARED_CLOUD，工作流运行时由调用方显式传入"
        ),
    )


def run(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
    data: dict[str, Any],
) -> int:
    """执行滚动调优，并为请求中的每种算法写出一个 Parquet。"""
    from runtime.apps.optimization import (
        OptimizationAlgorithm,
        OptimizationParameters,
        optimize_backtest,
    )
    from runtime.utils import logger

    run_arguments = model_input(parser, data, OptimizationParameters)
    output_target, storage = prepare_output_target(
        parser,
        arguments.output_dir,
        cloud=arguments.cloud,
    )
    with ExitStack() as stack:
        if storage is not None:
            stack.enter_context(storage)
        result = stack.enter_context(optimize_backtest(**run_arguments))
        outputs = [
            write_parquet(
                result.table(algorithm),
                f"{OptimizationAlgorithm(algorithm).value}.parquet",
                output_target=output_target,
                storage=storage,
            )
            for algorithm in run_arguments["algorithms"]
        ]
    logger.success(
        f"已保存 {len(outputs)} 个参数调优结果到 {output_target}"
    )
    return 0
