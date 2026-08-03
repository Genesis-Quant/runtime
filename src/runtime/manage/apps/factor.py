"""实现因子分析命令。"""

import argparse
from contextlib import ExitStack
from typing import Any

from .utils import (
    add_input_file_arguments,
    prepare_output_target,
    validate_model_input_fields,
    validate_output_names,
    write_parquet,
)

NAME = "factor"
HELP = "执行因子分析"
DESCRIPTION = "执行因子预处理、IC 和分组收益分析。"
OUTPUT_FILENAMES = {
    "processed_data": "factor_processed.parquet",
    "information_coefficient": "factor_information_coefficients.parquet",
    "group_returns": "factor_group_returns.parquet",
}
def configure_parser(parser: argparse.ArgumentParser) -> None:
    """注册因子分析命令参数。"""
    add_input_file_arguments(parser)
    parser.add_argument(
        "--output",
        nargs="+",
        choices=OUTPUT_FILENAMES,
        required=True,
        metavar="RESULT",
        help=f"需要输出的结果，可同时指定多个：{', '.join(OUTPUT_FILENAMES)}",
    )


def run(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
    data: dict[str, Any],
) -> int:
    """执行因子分析并写出选定的 Parquet 结果表。"""
    from runtime.apps.factor import FactorAnalysisParameters, analyze_factors
    from runtime.utils import logger

    run_fields = validate_model_input_fields(
        parser,
        data,
        FactorAnalysisParameters,
        extra_fields=frozenset({"output_dir"}),
    )
    validate_output_names(parser, arguments.output)
    output_target, storage = prepare_output_target(
        parser,
        data["output_dir"],
        input_file=arguments.input_file,
        output_cloud=arguments.output_cloud,
    )
    run_arguments = {
        name: data[name]
        for name in run_fields
        if name in data
    }
    outputs: list[str] = []
    with ExitStack() as stack:
        if storage is not None:
            stack.enter_context(storage)
        factor_result = stack.enter_context(
            analyze_factors(**run_arguments)
        )
        for output_name in arguments.output:
            outputs.append(write_parquet(
                getattr(factor_result, output_name),
                OUTPUT_FILENAMES[output_name],
                output_target=output_target,
                storage=storage,
            ))
    logger.success(f"因子分析结果已保存为 Parquet：{outputs}")
    return 0

