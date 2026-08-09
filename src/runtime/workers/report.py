"""根据 Worker 结果文件构造结构化汇总消息。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from runtime.messaging.models import StructuredMessage, TextMessageBlock
from runtime.workers.registry import (
    WORKER_DESCRIPTIONS,
    WORKER_ORDER,
    normalize_worker_names,
)
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
    selected_workers = normalize_worker_names(selected_workers)
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
    status_labels = {
        "SUCCESS": "成功",
        "FAILURE": "失败",
        "CANCELLED": "已取消",
        "SKIPPED": "已跳过",
        "MISSING": "缺失结果",
        "INVALID": "结果无效",
    }
    worker_details: list[dict[str, object]] = []
    worker_lines: list[str] = []
    for name in selected_workers:
        result = selected_results.get(name)
        description = WORKER_DESCRIPTIONS[name]
        if result is None:
            worker_status = "INVALID" if name in invalid else "MISSING"
            detail: dict[str, object] = {
                "worker": name,
                "description": description,
                "status": worker_status,
            }
            worker_lines.append(
                f"- {name}（{description}）：{status_labels[worker_status]}"
            )
        else:
            rows = int(result.metrics.get("rows_written", 0))
            workers_total = int(result.metrics.get("workers_total", 0))
            workers_completed = int(
                result.metrics.get("workers_completed", 0)
            )
            error = (
                f"{result.error.type}: {result.error.message}"
                if result.error is not None
                else None
            )
            detail = {
                "worker": name,
                "description": description,
                "status": result.status,
                "rows_written": rows,
                "duration_seconds": result.duration_seconds,
                "attempts": len(result.attempts),
                "workers_total": workers_total,
                "workers_completed": workers_completed,
                "error": error,
            }
            parts = [
                status_labels[result.status],
                f"写入 {rows:,} 行",
                f"耗时 {result.duration_seconds:.2f} 秒",
            ]
            if workers_total:
                parts.append(f"任务 {workers_completed:,}/{workers_total:,}")
            if len(result.attempts) > 1:
                parts.append(f"尝试 {len(result.attempts):,} 次")
            if error:
                parts.append(error)
            worker_lines.append(
                f"- {name}（{description}）：{'，'.join(parts)}"
            )
        worker_details.append(detail)
    blocks = [
        TextMessageBlock(text=summary),
        TextMessageBlock(
            text="Worker 明细：\n" + "\n".join(worker_lines)
        ),
    ]

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
            "worker_results": worker_details,
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


__all__ = [
    "IncrementalMessageStatus",
    "build_incremental_message",
    "load_worker_results",
]
