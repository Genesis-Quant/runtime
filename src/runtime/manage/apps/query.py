"""实现因子查询命令。"""

import argparse
from typing import Any

from runtime.utils.manage import (
    add_app_arguments,
    save_app_outputs,
    validate_input_fields,
)

NAME = "query"
HELP = "执行因子查询"
DESCRIPTION = "执行因子查询。"
OUTPUT_FILENAMES = {
    "source_data": "source_data.parquet",
    "computed_data": "computed_data.parquet",
    "filtered_data": "filtered_data.parquet",
    "data": "query.parquet",
}
INPUT_FIELDS = frozenset(("dataset_query",))


def configure_parser(parser: argparse.ArgumentParser) -> None:
    """注册查询命令参数。"""
    add_app_arguments(parser, OUTPUT_FILENAMES)


def run(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
    data: dict[str, Any],
) -> int:
    """执行查询并写出选定的 Parquet 结果表。"""
    from runtime.apps.query import execute_query
    from runtime.utils import logger

    validate_input_fields(
        parser,
        data,
        allowed=INPUT_FIELDS,
        required=INPUT_FIELDS,
    )
    outputs = save_app_outputs(parser, arguments, OUTPUT_FILENAMES, lambda: execute_query(data["dataset_query"]))
    logger.success(f"查询结果已保存为 Parquet：{outputs}")
    return 0

