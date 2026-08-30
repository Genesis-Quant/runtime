"""实现回测敏感性分析命令。"""

import argparse
from contextlib import ExitStack
from typing import Any

from runtime.config import ArenaSettings
from runtime.utils.manage import (
    boolean_argument,
    input_file_path,
    model_input,
    prepare_output_target,
    write_parquet_result,
    write_result_manifest,
)

NAME = "sensitivity"
HELP = "执行手续费或策略参数敏感性分析"
DESCRIPTION = "复用一次完整区间查询，在一个会话内运行全部敏感性组合。"


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input-file",
        type=input_file_path,
        required=True,
        metavar="PATH",
        help="包含完整敏感性分析请求的 UTF-8 JSON 文件",
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
        help="是否将结果上传到对象存储",
    )


def run(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
    data: dict[str, Any],
) -> int:
    from runtime.apps.sensitivity import (
        SensitivityParameters,
        analyze_backtest_sensitivity,
    )
    from runtime.utils import logger

    run_arguments = model_input(parser, data, SensitivityParameters)
    output_target, storage = prepare_output_target(
        parser,
        arguments.output_dir,
        cloud=arguments.cloud,
    )
    with ExitStack() as stack:
        if storage is not None:
            stack.enter_context(storage)
        result = stack.enter_context(analyze_backtest_sensitivity(**run_arguments))
        written = write_parquet_result(
            result.results,
            "results.parquet",
            output_target=output_target,
            storage=storage,
        )
        write_result_manifest(
            output_target,
            storage,
            {"results": ("results.parquet", written)},
        )
        output = written.location
    logger.success(f"已保存敏感性分析结果到 {output}")
    return 0
