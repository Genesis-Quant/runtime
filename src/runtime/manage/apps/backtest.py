"""实现日频回测命令。"""

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

NAME = "backtest"
HELP = "执行日频回测"
DESCRIPTION = "执行日频回测。"
OUTPUT_FILENAMES = {
    "trade_details": "trade_details.parquet",
    "daily_positions": "daily_positions.parquet",
    "daily_portfolios": "daily_portfolios.parquet",
    "return_summary": "return_summary.parquet",
    "daily_trading_statistics": "daily_trading_statistics.parquet",
    "engine_stat": "engine_stat.parquet",
}
def configure_parser(parser: argparse.ArgumentParser) -> None:
    """注册回测命令参数。"""
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
    """执行回测并写出选定的 Parquet 结果表。"""
    from runtime.apps.backtest import run_backtest
    from runtime.apps.backtest.schema import BacktestParameters
    from runtime.utils import logger

    run_fields = validate_model_input_fields(
        parser,
        data,
        BacktestParameters,
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
        backtest_result = stack.enter_context(
            run_backtest(**run_arguments)
        )
        for output_name in arguments.output:
            outputs.append(
                write_parquet(
                    getattr(backtest_result, output_name),
                    OUTPUT_FILENAMES[output_name],
                    output_target=output_target,
                    storage=storage,
                )
            )
    logger.success(f"回测结果已保存为 Parquet：{outputs}")
    return 0

