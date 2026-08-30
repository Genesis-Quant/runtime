"""实现因子分析命令。"""

import argparse
from typing import Any

from runtime.utils.manage import add_app_arguments, model_input, save_app_outputs

NAME = "factor"
HELP = "执行因子分析"
DESCRIPTION = "执行因子预处理、IC 和分组收益分析。"
OUTPUT_FILENAMES = {
    "processed_data": "factor_processed.parquet",
    "information_coefficient": "factor_information_coefficients.parquet",
    "group_returns": "factor_group_returns.parquet",
    "diagnostics": "factor_diagnostics.parquet",
}


def configure_parser(parser: argparse.ArgumentParser) -> None:
    """注册因子分析命令参数。"""
    add_app_arguments(parser, OUTPUT_FILENAMES)


def run(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
    data: dict[str, Any],
) -> int:
    """执行因子分析并写出选定的 Parquet 结果表。"""
    from runtime.apps.factor import FactorAnalysisParameters, analyze_factors
    from runtime.utils import logger

    run_arguments = model_input(parser, data, FactorAnalysisParameters)
    outputs = save_app_outputs(parser, arguments, OUTPUT_FILENAMES, lambda: analyze_factors(**run_arguments))
    logger.success(f"因子分析结果已保存为 Parquet：{outputs}")
    return 0

