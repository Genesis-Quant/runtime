"""实现因子分析命令。"""

import argparse
from contextlib import ExitStack
from typing import Any

import pandas as pd

from ._shared import (
    add_input_file_arguments,
    prepare_output_target,
    validate_input_fields,
    write_parquet,
)

NAME = "factor"
HELP = "执行因子分析"
DESCRIPTION = "执行因子预处理、IC 和分组收益分析。"
OUTPUT_FILENAMES = {
    "processed_data": "factor_processed.parquet",
    "information_coefficients": "factor_information_coefficients.parquet",
    "group_returns": "factor_group_returns.parquet",
}
RUN_FIELDS = (
    "dataset_query",
    "factor_columns",
    "return_columns",
    "n_groups",
    "preprocess",
    "market_value_column",
    "industry_level",
)
INPUT_FIELDS = frozenset((*RUN_FIELDS, "output_dir"))
REQUIRED_FIELDS = frozenset(
    (
        "dataset_query",
        "factor_columns",
        "return_columns",
        "output_dir",
    )
)


def configure_parser(parser: argparse.ArgumentParser) -> None:
    """注册因子分析命令参数。"""
    add_input_file_arguments(parser)


def combine_factor_tables(
    tables: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """合并按因子返回的同结构表，并添加 factor 标识列。"""
    frames: list[pd.DataFrame] = []
    for factor_name, data in tables.items():
        frame = data.copy()
        frame.insert(
            1 if "time" in frame.columns else 0,
            "factor",
            factor_name,
        )
        frames.append(frame)
    if not frames:
        raise ValueError("因子分析没有返回任何因子表")
    return pd.concat(frames, ignore_index=True)


def run(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
    data: dict[str, Any],
) -> int:
    """执行因子分析并写出三张固定名称的 Parquet。"""
    from core.apps.factor import analyze_factors
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
    run_arguments = {
        name: data[name]
        for name in RUN_FIELDS
        if name in data
    }
    outputs: list[str] = []
    with ExitStack() as stack:
        if storage is not None:
            stack.enter_context(storage)
        factor_result = stack.enter_context(
            analyze_factors(**run_arguments)
        )
        outputs.append(
            write_parquet(
                factor_result.processed_data,
                OUTPUT_FILENAMES["processed_data"],
                output_target=output_target,
                storage=storage,
            )
        )
        outputs.append(
            write_parquet(
                combine_factor_tables(
                    factor_result.information_coefficients
                ),
                OUTPUT_FILENAMES["information_coefficients"],
                output_target=output_target,
                storage=storage,
            )
        )
        outputs.append(
            write_parquet(
                combine_factor_tables(
                    factor_result.all_group_returns
                ),
                OUTPUT_FILENAMES["group_returns"],
                output_target=output_target,
                storage=storage,
            )
        )
    logger.success(f"因子分析结果已保存为 Parquet：{outputs}")
    return 0

