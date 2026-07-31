"""实现查询、因子分析与回测应用命令。"""

import argparse
from collections.abc import Sequence
from contextlib import ExitStack
import json
from pathlib import Path
from typing import Any

import pandas as pd

from core.utils.storage import (
    ObjectStorage,
    ObjectStorageConfigurationError,
)


QUERY_OUTPUT_FILENAME = "query.parquet"
FACTOR_OUTPUT_FILENAMES = {
    "processed_data": "factor_processed.parquet",
    "information_coefficients": "factor_information_coefficients.parquet",
    "group_returns": "factor_group_returns.parquet",
}
BACKTEST_OUTPUT_NAMES = (
    "trade_details",
    "daily_positions",
    "daily_portfolios",
    "daily_trading_statistics",
)
QUERY_INPUT_FIELDS = frozenset(("dataset_query", "output_dir"))
FACTOR_RUN_FIELDS = (
    "dataset_query",
    "factor_columns",
    "return_columns",
    "n_groups",
    "preprocess",
    "market_value_column",
    "industry_level",
)
FACTOR_INPUT_FIELDS = frozenset((*FACTOR_RUN_FIELDS, "output_dir"))
BACKTEST_RUN_FIELDS = (
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
BACKTEST_INPUT_FIELDS = frozenset(
    (*BACKTEST_RUN_FIELDS, "output_dir", "output")
)


def input_file_path(value: str) -> Path:
    """解析并检查输入 JSON 文件路径。"""
    path = Path(value).expanduser()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"输入文件不存在或不是文件：{path}")
    return path.resolve()


def load_input_file(
        parser: argparse.ArgumentParser,
        path: Path,
) -> dict[str, Any]:
    """读取 UTF-8 JSON 对象，格式错误时按命令行参数错误退出。"""
    try:
        content = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        parser.error(f"无法读取输入文件 {path}：{error}")
    try:
        result = json.loads(content)
    except json.JSONDecodeError as error:
        parser.error(
            f"输入文件 {path} 不是有效 JSON："
            f"第 {error.lineno} 行第 {error.colno} 列，{error.msg}"
        )
    if not isinstance(result, dict):
        parser.error(f"输入文件 {path} 的顶层必须是 JSON 对象")
    return result


def validate_input_fields(
        parser: argparse.ArgumentParser,
        data: dict[str, Any],
        *,
        allowed: frozenset[str],
        required: frozenset[str],
) -> None:
    """拒绝输入文件中的未知字段和缺失必填字段。"""
    if unknown := sorted(set(data) - allowed):
        parser.error(f"输入文件包含未知字段：{unknown}")
    if missing := sorted(required - set(data)):
        parser.error(f"输入文件缺少必填字段：{missing}")


def resolve_output_dir(
        parser: argparse.ArgumentParser,
        value: Any,
        *,
        input_file: Path,
) -> Path:
    """解析输出目录；相对路径以输入文件所在目录为基准。"""
    if not isinstance(value, str) or not value.strip():
        parser.error("input_file.output_dir 必须是非空字符串")
    output_dir = Path(value).expanduser()
    if not output_dir.is_absolute():
        output_dir = input_file.parent / output_dir
    return output_dir.resolve()


def resolve_object_prefix(
        parser: argparse.ArgumentParser,
        value: Any,
) -> str:
    """校验云端 output_dir，并转换为 S3 对象键前缀。"""
    if not isinstance(value, str) or not value.strip():
        parser.error("input_file.output_dir 必须是非空字符串")
    normalized = value.strip().replace("\\", "/").rstrip("/")
    if (
        not normalized
        or normalized.startswith("/")
        or (len(normalized) >= 2 and normalized[1] == ":")
        or "://" in normalized
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
    ):
        parser.error(
            "云端 input_file.output_dir 必须是 bucket 内的相对对象路径"
        )
    return normalized


def prepare_output_target(
        parser: argparse.ArgumentParser,
        output_dir: Any,
        *,
        input_file: Path,
        output_cloud: bool,
) -> tuple[Path | str, ObjectStorage | None]:
    """创建本地或对象存储输出目标。"""
    if output_cloud:
        prefix = resolve_object_prefix(parser, output_dir)
        try:
            storage = ObjectStorage.from_env()
        except ObjectStorageConfigurationError as error:
            parser.error(str(error))
        return prefix, storage

    local_dir = resolve_output_dir(
        parser,
        output_dir,
        input_file=input_file,
    )
    local_dir.mkdir(parents=True, exist_ok=True)
    return local_dir, None


def write_parquet(
        data: Any,
        filename: str,
        *,
        output_target: Path | str,
        storage: ObjectStorage | None,
) -> str:
    """将结果写入本地目录或对象存储。"""
    if storage is not None:
        return storage.upload_parquet(
            data,
            f"{output_target}/{filename}",
        )

    if not isinstance(output_target, Path):
        raise TypeError("本地输出目标必须是 Path")
    output = output_target / filename
    data.to_parquet(output, index=False)
    return str(output.resolve())


def validate_backtest_output_names(
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
    unsupported = sorted(set(value) - set(BACKTEST_OUTPUT_NAMES))
    if unsupported:
        parser.error(
            f"不支持的回测输出：{unsupported}；"
            f"可选值：{list(BACKTEST_OUTPUT_NAMES)}"
        )
    if len(value) != len(set(value)):
        parser.error("input_file.output 中的名称不能重复")
    return value


def combine_factor_outputs(
        tables: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """把按因子返回的同结构表合并，并添加明确的 factor 列。"""
    frames: list[pd.DataFrame] = []
    for factor, data in tables.items():
        frame = data.copy()
        frame.insert(
            1 if "time" in frame.columns else 0,
            "factor",
            factor,
        )
        frames.append(frame)
    if not frames:
        raise ValueError("因子分析没有返回任何因子表")
    return pd.concat(frames, ignore_index=True)


def add_input_file_argument(parser: argparse.ArgumentParser) -> None:
    """添加统一的输入文件和输出位置参数。"""
    parser.add_argument(
        "--input-file",
        type=input_file_path,
        required=True,
        metavar="PATH",
        help="包含全部应用参数的 UTF-8 JSON 文件",
    )
    parser.add_argument(
        "--output-cloud",
        action="store_true",
        default=False,
        help="将 Parquet 上传到对象存储；默认写入本地目录",
    )


def build_parser(*, prog: str | None = None) -> argparse.ArgumentParser:
    """创建应用命令解析器。"""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="运行查询、因子分析或回测应用。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  core-manage apps query --input-file query.json\n"
            "  core-manage apps factor --input-file factor.json\n"
            "  core-manage apps backtest --input-file backtest.json"
        ),
    )
    commands = parser.add_subparsers(
        dest="app",
        metavar="APP",
        required=True,
    )

    query_parser = commands.add_parser(
        "query",
        help="执行因子查询",
        description="执行因子查询。",
        allow_abbrev=False,
    )
    add_input_file_argument(query_parser)

    factor_parser = commands.add_parser(
        "factor",
        help="执行因子分析",
        description="执行因子预处理、IC 和分组收益分析。",
        allow_abbrev=False,
    )
    add_input_file_argument(factor_parser)

    backtest_parser = commands.add_parser(
        "backtest",
        help="执行日频回测",
        description="执行日频回测。",
        allow_abbrev=False,
    )
    add_input_file_argument(backtest_parser)
    return parser


def main(
        argv: Sequence[str] | None = None,
        *,
        prog: str | None = None,
) -> int:
    """解析参数并运行指定应用。"""
    parser = build_parser(prog=prog)
    arguments = parser.parse_args(argv)
    data = load_input_file(parser, arguments.input_file)

    if arguments.app == "query":
        from core.apps.query import execute_query
        from core.utils import logger

        validate_input_fields(
            parser,
            data,
            allowed=QUERY_INPUT_FIELDS,
            required=QUERY_INPUT_FIELDS,
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
                QUERY_OUTPUT_FILENAME,
                output_target=output_target,
                storage=storage,
            )
        logger.success(f"查询结果已保存为 Parquet：{output}")
        return 0

    if arguments.app == "factor":
        from core.apps.factor import analyze_factors
        from core.utils import logger

        validate_input_fields(
            parser,
            data,
            allowed=FACTOR_INPUT_FIELDS,
            required=frozenset(
                (
                    "dataset_query",
                    "factor_columns",
                    "return_columns",
                    "output_dir",
                )
            ),
        )
        output_target, storage = prepare_output_target(
            parser,
            data["output_dir"],
            input_file=arguments.input_file,
            output_cloud=arguments.output_cloud,
        )
        run_arguments = {
            name: data[name]
            for name in FACTOR_RUN_FIELDS
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
                    FACTOR_OUTPUT_FILENAMES["processed_data"],
                    output_target=output_target,
                    storage=storage,
                )
            )
            outputs.append(
                write_parquet(
                    combine_factor_outputs(
                        factor_result.information_coefficients
                    ),
                    FACTOR_OUTPUT_FILENAMES[
                        "information_coefficients"
                    ],
                    output_target=output_target,
                    storage=storage,
                )
            )
            outputs.append(
                write_parquet(
                    combine_factor_outputs(
                        factor_result.all_group_returns
                    ),
                    FACTOR_OUTPUT_FILENAMES["group_returns"],
                    output_target=output_target,
                    storage=storage,
                )
            )
        logger.success(f"因子分析结果已保存为 Parquet：{outputs}")
        return 0

    from core.apps.backtest import run_backtest
    from core.utils import logger

    validate_input_fields(
        parser,
        data,
        allowed=BACKTEST_INPUT_FIELDS,
        required=frozenset(("dataset_query", "callbacks", "output_dir")),
    )
    output_target, storage = prepare_output_target(
        parser,
        data["output_dir"],
        input_file=arguments.input_file,
        output_cloud=arguments.output_cloud,
    )
    output_names = (
        validate_backtest_output_names(parser, data["output"])
        if "output" in data
        else list(BACKTEST_OUTPUT_NAMES)
    )
    run_arguments = {
        name: data[name]
        for name in BACKTEST_RUN_FIELDS
        if name in data
    }
    outputs: list[str] = []
    with ExitStack() as stack:
        if storage is not None:
            stack.enter_context(storage)
        backtest_result = stack.enter_context(run_backtest(**run_arguments))
        for output_name in output_names:
            outputs.append(
                write_parquet(
                    getattr(backtest_result, output_name),
                    f"{output_name}.parquet",
                    output_target=output_target,
                    storage=storage,
                )
            )
    logger.success(
        f"回测结果已保存为 Parquet：{outputs}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
