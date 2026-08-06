"""实现日频回测命令。"""

import argparse
from typing import Any

from runtime.utils.manage import add_app_arguments, model_input, save_app_outputs

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
    add_app_arguments(parser, OUTPUT_FILENAMES)


def run(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
    data: dict[str, Any],
) -> int:
    """执行回测并写出选定的 Parquet 结果表。"""
    from runtime.apps.backtest import run_backtest
    from runtime.apps.backtest.schema import BacktestParameters
    from runtime.utils import logger

    run_arguments = model_input(parser, data, BacktestParameters)
    outputs = save_app_outputs(parser, arguments, OUTPUT_FILENAMES, lambda: run_backtest(**run_arguments))
    logger.success(f"回测结果已保存为 Parquet：{outputs}")
    return 0

