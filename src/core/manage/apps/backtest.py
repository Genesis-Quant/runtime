"""实现日频回测命令。"""

import argparse
from contextlib import ExitStack
from typing import Any

from ._shared import (
    add_input_file_arguments,
    prepare_output_target,
    validate_input_fields,
    write_parquet,
)

NAME = "backtest"
HELP = "执行日频回测"
DESCRIPTION = "执行日频回测。"
OUTPUT_NAMES = (
    "trade_details",
    "daily_positions",
    "daily_portfolios",
    "daily_trading_statistics",
)
RUN_FIELDS = (
    "dataset_query",
    "callbacks",
    "utils",
    "codes_query",
    "adj",
    "name",
    "config",
    "annual_trading_days",
    "risk_free_rate",
    "source_ref",
    "message_ref",
)
INPUT_FIELDS = frozenset((*RUN_FIELDS, "output_dir", "output"))
REQUIRED_FIELDS = frozenset(("dataset_query", "callbacks", "output_dir"))


def configure_parser(parser: argparse.ArgumentParser) -> None:
    """注册回测命令参数。"""
    add_input_file_arguments(parser)


def validate_output_names(
    parser: argparse.ArgumentParser,
    value: Any,
) -> list[str]:
    """校验需要保存的回测结果表名称。"""
    if not isinstance(value, list):
        parser.error("input_file.output 必须是 JSON 数组")
    if not all(isinstance(name, str) for name in value):
        parser.error("input_file.output 中的名称必须全部是字符串")
    if not value:
        parser.error("input_file.output 至少需要指定一张表")
    unsupported = sorted(set(value) - set(OUTPUT_NAMES))
    if unsupported:
        parser.error(
            f"不支持的回测输出：{unsupported}；"
            f"可选值：{list(OUTPUT_NAMES)}"
        )
    if len(value) != len(set(value)):
        parser.error("input_file.output 中的名称不能重复")
    return value


def run(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
    data: dict[str, Any],
) -> int:
    """执行回测并写出选定的 Parquet 结果表。"""
    from core.apps.backtest import run_backtest
    from core.utils import logger

    validate_input_fields(
        parser,
        data,
        allowed=INPUT_FIELDS,
        required=REQUIRED_FIELDS,
    )
    output_target, storage = prepare_output_target(
        parser,
        data["output_dir"],
        input_file=arguments.input_file,
        output_cloud=arguments.output_cloud,
    )
    output_names = (
        validate_output_names(parser, data["output"])
        if "output" in data
        else list(OUTPUT_NAMES)
    )
    run_arguments = {
        name: data[name]
        for name in RUN_FIELDS
        if name in data
    }
    outputs: list[str] = []
    with ExitStack() as stack:
        if storage is not None:
            stack.enter_context(storage)
        backtest_result = stack.enter_context(
            run_backtest(**run_arguments)
        )
        for output_name in output_names:
            outputs.append(
                write_parquet(
                    getattr(backtest_result, output_name),
                    f"{output_name}.parquet",
                    output_target=output_target,
                    storage=storage,
                )
            )
    logger.success(f"回测结果已保存为 Parquet：{outputs}")
    return 0

