"""实现因子查询命令。"""

import argparse
from contextlib import ExitStack
from typing import Any

from ._shared import (
    add_input_file_arguments,
    prepare_output_target,
    validate_input_fields,
    write_parquet,
)

NAME = "query"
HELP = "执行因子查询"
DESCRIPTION = "执行因子查询。"
OUTPUT_FILENAME = "query.parquet"
INPUT_FIELDS = frozenset(("dataset_query", "output_dir"))


def configure_parser(parser: argparse.ArgumentParser) -> None:
    """注册查询命令参数。"""
    add_input_file_arguments(parser)


def run(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
    data: dict[str, Any],
) -> int:
    """执行查询并写出固定名称的 Parquet。"""
    from core.apps.query import execute_query
    from core.utils import logger

    validate_input_fields(
        parser,
        data,
        allowed=INPUT_FIELDS,
        required=INPUT_FIELDS,
    )
    output_target, storage = prepare_output_target(
        parser,
        data["output_dir"],
        input_file=arguments.input_file,
        output_cloud=arguments.output_cloud,
    )
    with ExitStack() as stack:
        if storage is not None:
            stack.enter_context(storage)
        query_result = stack.enter_context(
            execute_query(data["dataset_query"])
        )
        output = write_parquet(
            query_result.data,
            OUTPUT_FILENAME,
            output_target=output_target,
            storage=storage,
        )
    logger.success(f"查询结果已保存为 Parquet：{output}")
    return 0

