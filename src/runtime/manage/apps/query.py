"""实现因子查询命令。"""

import argparse
from contextlib import ExitStack
from typing import Any

from .utils import (
    add_input_file_arguments,
    prepare_output_target,
    validate_input_fields,
    validate_output_names,
    write_parquet,
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
INPUT_FIELDS = frozenset(("dataset_query", "output_dir"))


def configure_parser(parser: argparse.ArgumentParser) -> None:
    """注册查询命令参数。"""
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
    """执行查询并写出选定的 Parquet 结果表。"""
    from runtime.apps.query import execute_query
    from runtime.utils import logger

    validate_input_fields(
        parser,
        data,
        allowed=INPUT_FIELDS,
        required=INPUT_FIELDS,
    )
    validate_output_names(parser, arguments.output)
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
        outputs = [
            write_parquet(
                getattr(query_result, output_name),
                OUTPUT_FILENAMES[output_name],
                output_target=output_target,
                storage=storage,
            )
            for output_name in arguments.output
        ]
    logger.success(f"查询结果已保存为 Parquet：{outputs}")
    return 0

