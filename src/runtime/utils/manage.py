"""提供管理命令共用的输入、输出和对象存储能力。"""

import argparse
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from dataclasses import asdict
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from pydantic import BaseModel

from runtime.config import ArenaSettings
from runtime.utils.result import SessionResult
from runtime.utils.storage import (
    MAX_RESULT_MANIFEST_SIZE,
    ObjectStorage,
    ObjectStorageConfigurationError,
    RESULT_MANIFEST_FILENAME,
    RESULT_MANIFEST_VERSION,
    StoredParquet,
    parquet_content_metadata,
)


def input_file_path(value: str) -> Path:
    """解析并检查输入 JSON 文件路径。"""
    path = Path(value).expanduser()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"输入文件不存在或不是文件：{path}")
    return path.resolve()


def boolean_argument(value: str) -> bool:
    """解析命令行中的显式 true/false。"""
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise argparse.ArgumentTypeError("必须是 true 或 false")
    return normalized == "true"


def add_app_arguments(parser: argparse.ArgumentParser, output_filenames: Mapping[str, str]) -> None:
    """添加应用统一使用的输入和输出参数。"""
    parser.add_argument(
        "--input-file",
        type=input_file_path,
        required=True,
        metavar="PATH",
        help="包含全部应用参数的 UTF-8 JSON 文件",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        metavar="DIR",
        help="本地输出目录或 bucket 内的相对对象路径",
    )
    parser.add_argument(
        "--cloud",
        type=boolean_argument,
        default=ArenaSettings.SHARED_CLOUD,
        help=(
            "是否将结果上传到对象存储；直接运行时默认读取 "
            "ARENA_SHARED_CLOUD，工作流运行时由调用方显式传入"
        ),
    )
    parser.add_argument(
        "--output",
        nargs="+",
        choices=output_filenames,
        required=True,
        metavar="RESULT",
        help=f"需要输出的结果，可同时指定多个：{', '.join(output_filenames)}",
    )


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


def model_input(
    parser: argparse.ArgumentParser,
    data: dict[str, Any],
    model: type[BaseModel],
    *,
    extra_fields: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """校验并返回 Pydantic 模型声明的命令输入。"""
    model_fields = tuple(model.model_fields.keys())
    required = frozenset(
        name for name, field in model.model_fields.items() if field.is_required()
    )
    validate_input_fields(
        parser,
        data,
        allowed=frozenset(model_fields) | extra_fields,
        required=required | extra_fields,
    )
    return {name: data[name] for name in model_fields if name in data}


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
) -> Path:
    """解析命令行指定的本地输出目录。"""
    if not isinstance(value, str) or not value.strip():
        parser.error("--output-dir 必须是非空字符串")
    output_dir = Path(value).expanduser()
    return output_dir.resolve()


def resolve_object_prefix(
    parser: argparse.ArgumentParser,
    value: Any,
) -> str:
    """校验云端 output_dir，并转换为 S3 对象键前缀。"""
    if not isinstance(value, str) or not value.strip():
        parser.error("--output-dir 必须是非空字符串")
    normalized = value.strip().replace("\\", "/").rstrip("/")
    if (
        not normalized
        or normalized.startswith("/")
        or (len(normalized) >= 2 and normalized[1] == ":")
        or "://" in normalized
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
    ):
        parser.error(
            "云端 --output-dir 必须是 bucket 内的相对对象路径"
        )
    return normalized


def prepare_output_target(
    parser: argparse.ArgumentParser,
    output_dir: Any,
    *,
    cloud: bool,
) -> tuple[Path | str, ObjectStorage | None]:
    """创建本地或对象存储输出目标。"""
    if cloud:
        prefix = resolve_object_prefix(parser, output_dir)
        try:
            storage = ObjectStorage.from_env()
        except ObjectStorageConfigurationError as error:
            parser.error(str(error))
        return prefix, storage

    local_dir = resolve_output_dir(parser, output_dir)
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
    return write_parquet_result(
        data,
        filename,
        output_target=output_target,
        storage=storage,
    ).location


def write_parquet_result(
    data: Any,
    filename: str,
    *,
    output_target: Path | str,
    storage: ObjectStorage | None,
) -> StoredParquet:
    """Write one Parquet and return metadata bound to the written snapshot."""
    if storage is not None:
        return storage.upload_parquet_result(
            data,
            f"{output_target}/{filename}",
        )

    if not isinstance(output_target, Path):
        raise TypeError("本地输出目标必须是 Path")
    output = output_target / filename
    data.to_parquet(output, index=False)
    with output.open("rb") as source:
        file_stat = os.fstat(source.fileno())
        metadata = parquet_content_metadata(source)
        after = os.fstat(source.fileno())
    snapshot = (
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
        getattr(file_stat, "st_ino", 0),
    )
    if snapshot != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        getattr(after, "st_ino", 0),
    ) or metadata.size != file_stat.st_size:
        raise OSError(f"Parquet 在生成结果清单时发生变化：{output}")
    return StoredParquet(
        location=str(output.resolve()),
        size=file_stat.st_size,
        modified_at=datetime.fromtimestamp(file_stat.st_mtime, UTC),
        # A bind-mounted file can expose different inode/ctime values in the
        # Worker and Backend containers. Size + mtime still bind the manifest
        # to the freshly reset workspace output without defeating fast reads.
        snapshot_token=None,
        row_count=metadata.row_count,
        columns=metadata.columns,
        sha256=metadata.sha256,
    )


def write_result_manifest(
    output_target: Path | str,
    storage: ObjectStorage | None,
    files: Mapping[str, tuple[str, StoredParquet]],
) -> str:
    """Persist the small output manifest only after every Parquet succeeded."""
    payload = {
        "version": RESULT_MANIFEST_VERSION,
        "files": {
            name: {
                "filename": filename,
                "size": result.size,
                "modified_at": result.modified_at.isoformat(),
                "snapshot_token": result.snapshot_token,
                "row_count": result.row_count,
                "columns": [asdict(column) for column in result.columns],
                "sha256": result.sha256,
            }
            for name, (filename, result) in files.items()
        },
    }
    data = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(data) > MAX_RESULT_MANIFEST_SIZE:
        raise OSError("结果清单超过大小限制")
    if storage is not None:
        return storage.upload_json(
            data,
            f"{output_target}/{RESULT_MANIFEST_FILENAME}",
        )
    if not isinstance(output_target, Path):
        raise TypeError("本地输出目标必须是 Path")
    manifest = output_target / RESULT_MANIFEST_FILENAME
    if manifest.is_symlink():
        raise OSError("结果清单路径不能是符号链接")
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=output_target,
            prefix=f"{RESULT_MANIFEST_FILENAME}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(manifest)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return str(manifest.resolve())


def save_app_outputs(
    parser: argparse.ArgumentParser,
    arguments: argparse.Namespace,
    output_filenames: Mapping[str, str],
    result_factory: Callable[[], SessionResult],
) -> list[str]:
    """运行应用并将选定结果写入本地目录或对象存储。"""
    validate_output_names(parser, arguments.output)
    output_target, storage = prepare_output_target(parser, arguments.output_dir, cloud=arguments.cloud)
    with ExitStack() as stack:
        if storage is not None:
            stack.enter_context(storage)
        result = stack.enter_context(result_factory())
        outputs: list[str] = []
        manifest_files: dict[str, tuple[str, StoredParquet]] = {}
        for output_name in arguments.output:
            data = getattr(result, output_name)
            filename = output_filenames[output_name]
            written = write_parquet_result(
                data,
                filename,
                output_target=output_target,
                storage=storage,
            )
            outputs.append(written.location)
            manifest_files[output_name] = (filename, written)
        write_result_manifest(output_target, storage, manifest_files)
        return outputs

