"""根据 Worker 结果文件构造结构化汇总消息。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from runtime.messaging.models import StructuredMessage, TextMessageBlock
from runtime.workers.registry import WORKER_ORDER
from runtime.workers.result import WorkerResult

IncrementalMessageStatus = Literal[
    "SUCCESS",
    "FAILURE",
    "CANCELLED",
    "UNKNOWN",
]


def build_incremental_message(
    output_dir: str,
    *,
    job_id: str | None,
    selected_workers: tuple[str, ...],
) -> StructuredMessage:
    """汇总同一次增量工作流的 Worker 输出。"""
    normalized_output_dir = output_dir.strip()
    if not normalized_output_dir:
        return unknown_incremental_message(job_id, selected_workers)

    directory = Path(normalized_output_dir).expanduser().resolve()
    results, invalid_results = load_worker_results(directory, job_id=job_id)
    selected = set(selected_workers)
    invalid_workers = [
        name for name in invalid_results if name in selected
    ]
    selected_results = {
        name: result
        for name, result in results.items()
        if name in selected
    }
    invalid = set(invalid_workers)
    missing_workers = [
        name
        for name in selected_workers
        if name not in selected_results and name not in invalid
    ]
    succeeded_workers = [
        name
        for name in selected_workers
        if selected_results.get(name) is not None
        and selected_results[name].status == "SUCCESS"
    ]
    failed_workers = [
        name
        for name in selected_workers
        if selected_results.get(name) is not None
        and selected_results[name].status in {"FAILURE", "SKIPPED"}
    ]
    cancelled_workers = [
        name
        for name in selected_workers
        if selected_results.get(name) is not None
        and selected_results[name].status == "CANCELLED"
    ]
    skipped_workers = [
        name for name, result in results.items() if result.status == "SKIPPED"
    ]
    worker_errors = {
        name: (
            f"{result.error.type}: {result.error.message}"
            if result.error is not None
            else "Worker 返回失败状态"
        )
        for name, result in selected_results.items()
        if result.status == "FAILURE"
    }
    status: IncrementalMessageStatus
    if failed_workers or missing_workers or invalid_workers:
        status = "FAILURE"
    elif cancelled_workers:
        status = "CANCELLED"
    else:
        status = "SUCCESS"

    rows_written = sum(
        int(result.metrics.get("rows_written", 0))
        for result in selected_results.values()
    )
    summary = (
        f"状态：{status}\n"
        f"Job ID：{job_id or '—'}\n"
        f"Worker：{len(selected_workers)} 个，成功 {len(succeeded_workers)}，"
        f"失败 {len(failed_workers) + len(invalid_workers)}，"
        f"取消 {len(cancelled_workers)}，缺失 {len(missing_workers)}\n"
        f"写入行数：{rows_written:,}"
    )
    details = detail_lines(
        failed_workers=failed_workers,
        cancelled_workers=cancelled_workers,
        missing_workers=missing_workers,
        invalid_workers=invalid_workers,
        worker_errors=worker_errors,
    )
    blocks = [TextMessageBlock(text=summary)]
    if details:
        blocks.append(TextMessageBlock(text="\n".join(details)))

    return StructuredMessage(
        title={
            "SUCCESS": "增量更新完成",
            "FAILURE": "增量更新失败",
            "CANCELLED": "增量更新已取消",
            "UNKNOWN": "增量更新结果不可用",
        }[status],
        blocks=blocks,
        metadata={
            "workflow": "incremental-update",
            "job_id": job_id,
            "status": status,
            "selected_workers": list(selected_workers),
            "succeeded_workers": succeeded_workers,
            "failed_workers": failed_workers,
            "cancelled_workers": cancelled_workers,
            "skipped_workers": skipped_workers,
            "missing_workers": missing_workers,
            "invalid_workers": invalid_workers,
            "worker_errors": worker_errors,
            "rows_written": rows_written,
        },
    )


def unknown_incremental_message(
    job_id: str | None,
    selected_workers: tuple[str, ...],
) -> StructuredMessage:
    """在禁用 Worker 输出时生成明确的不可汇总消息。"""
    return StructuredMessage(
        title="增量更新结果不可用",
        blocks=[
            TextMessageBlock(
                text=(
                    f"Job ID：{job_id or '—'}\n"
                    "本次工作流未指定 output_dir，无法读取 Worker 结构化结果。"
                )
            )
        ],
        metadata={
            "workflow": "incremental-update",
            "job_id": job_id,
            "status": "UNKNOWN",
            "selected_workers": list(selected_workers),
        },
    )


def load_worker_results(
    directory: Path,
    *,
    job_id: str | None,
) -> tuple[dict[str, WorkerResult], list[str]]:
    """只读取注册 Worker 的固定文件，拒绝混入其他任务结果。"""
    results: dict[str, WorkerResult] = {}
    invalid: list[str] = []
    for name in WORKER_ORDER:
        path = directory / f"{name}.json"
        if not path.is_file():
            continue
        try:
            result = WorkerResult.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            invalid.append(name)
            continue
        if result.worker != name or (job_id and result.job_id != job_id):
            invalid.append(name)
            continue
        results[name] = result
    return results, invalid


def detail_lines(
    *,
    failed_workers: list[str],
    cancelled_workers: list[str],
    missing_workers: list[str],
    invalid_workers: list[str],
    worker_errors: dict[str, str],
) -> list[str]:
    """构造只包含异常项的简短文本。"""
    groups: tuple[tuple[str, list[str]], ...] = (
        ("失败", failed_workers),
        ("取消", cancelled_workers),
        ("缺失结果", missing_workers),
        ("无效结果", invalid_workers),
    )
    lines = [
        f"{label}：{', '.join(values)}"
        for label, values in groups
        if values
    ]
    lines.extend(
        f"{name}：{error}"
        for name, error in worker_errors.items()
    )
    return lines


__all__ = [
    "IncrementalMessageStatus",
    "build_incremental_message",
    "load_worker_results",
]
