"""提供应用命令共用的输入、输出和对象存储能力。"""

import argparse
import json
from pathlib import Path
from typing import Any

from runtime.utils.storage import (
    ObjectStorage,
    ObjectStorageConfigurationError,
)


def input_file_path(value: str) -> Path:
    """解析并检查输入 JSON 文件路径。"""
    path = Path(value).expanduser()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"输入文件不存在或不是文件：{path}")
    return path.resolve()


def add_input_file_arguments(parser: argparse.ArgumentParser) -> None:
    """添加所有应用统一使用的输入文件和输出位置参数。"""
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


def validate_model_input_fields(
    parser: argparse.ArgumentParser,
    data: dict[str, Any],
    model: type[Any],
    *,
    extra_fields: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """使用 Pydantic 模型字段生成命令输入的允许和必填字段。"""
    model_fields = tuple(model.model_fields)
    required = frozenset(
        name for name, field in model.model_fields.items() if field.is_required()
    )
    validate_input_fields(
        parser,
        data,
        allowed=frozenset(model_fields) | extra_fields,
        required=required | extra_fields,
    )
    return model_fields


def validate_output_names(
    parser: argparse.ArgumentParser,
    values: list[str],
) -> None:
    """拒绝命令行中重复请求同一个结果。"""
    if len(values) != len(set(values)):
        parser.error("--output 中的名称不能重复")


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

