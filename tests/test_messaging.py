from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from runtime.messaging import (
    SpecialMessageBlock,
    StructuredMessage,
    TextMessageBlock,
    normalize_channel_name,
    read_message,
    send_message,
    write_message,
)
from runtime.workers.report import build_incremental_message
from runtime.workers.result import (
    WorkerAttempt,
    WorkerError,
    WorkerResult,
    WorkerStatus,
    write_worker_result,
)


class MessagingTests(unittest.TestCase):
    def test_incremental_message_normalizes_worker_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            write_worker_result(
                directory,
                worker_result("daily", "SUCCESS", rows_written=12),
            )

            message = build_incremental_message(
                directory,
                job_id="job-1",
                selected_workers=("stock-daily",),
            )

            self.assertEqual(message.metadata["status"], "SUCCESS")
            self.assertEqual(message.metadata["selected_workers"], ["daily"])
            self.assertEqual(message.metadata["succeeded_workers"], ["daily"])
            self.assertEqual(message.metadata["rows_written"], 12)
            self.assertEqual(
                message.metadata["worker_results"],
                [
                    {
                        "worker": "daily",
                        "description": "全市场未复权日行情",
                        "status": "SUCCESS",
                        "rows_written": 12,
                        "duration_seconds": 0,
                        "attempts": 1,
                        "workers_total": 0,
                        "workers_completed": 0,
                        "error": None,
                    }
                ],
            )

    def test_incremental_message_summarizes_worker_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            write_worker_result(
                directory,
                worker_result("daily", "SUCCESS", rows_written=12),
            )
            write_worker_result(
                directory,
                worker_result(
                    "limit",
                    "FAILURE",
                    error=WorkerError(
                        type="RuntimeError",
                        message="boom",
                    ),
                ),
            )

            message = build_incremental_message(
                directory,
                job_id="job-1",
                selected_workers=("daily", "limit"),
            )
            path = write_message(Path(directory) / "message.json", message)

            self.assertEqual(message.metadata["status"], "FAILURE")
            self.assertEqual(message.metadata["rows_written"], 12)
            self.assertEqual(
                message.metadata["worker_errors"],
                {"limit": "RuntimeError: boom"},
            )
            self.assertEqual(
                message.metadata["worker_results"],
                [
                    {
                        "worker": "daily",
                        "description": "全市场未复权日行情",
                        "status": "SUCCESS",
                        "rows_written": 12,
                        "duration_seconds": 0,
                        "attempts": 1,
                        "workers_total": 0,
                        "workers_completed": 0,
                        "error": None,
                    },
                    {
                        "worker": "limit",
                        "description": "全市场每日涨跌停价格",
                        "status": "FAILURE",
                        "rows_written": 0,
                        "duration_seconds": 0,
                        "attempts": 1,
                        "workers_total": 0,
                        "workers_completed": 0,
                        "error": "RuntimeError: boom",
                    },
                ],
            )
            detail_block = message.blocks[1]
            self.assertIsInstance(detail_block, TextMessageBlock)
            assert isinstance(detail_block, TextMessageBlock)
            self.assertEqual(
                detail_block.text,
                "Worker 明细：\n"
                "- daily（全市场未复权日行情）：成功，写入 12 行，耗时 0.00 秒\n"
                "- limit（全市场每日涨跌停价格）：失败，写入 0 行，耗时 0.00 秒，RuntimeError: boom",
            )
            self.assertEqual(path, Path(directory).resolve() / "message.json")
            self.assertEqual(read_message(path), message)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["title"],
                "增量更新失败",
            )

    def test_console_ignores_channel_specific_only_message(self) -> None:
        message = StructuredMessage(
            title="channel card",
            blocks=[
                SpecialMessageBlock(
                    channel="wechat",
                    format="card",
                    payload={},
                )
            ],
        )
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            delivery = send_message(message, "console")

        self.assertEqual(delivery.status, "IGNORED")
        self.assertEqual(output.getvalue(), "")

    def test_console_is_default_channel(self) -> None:
        self.assertEqual(normalize_channel_name(None), "console")
        self.assertEqual(normalize_channel_name(""), "console")
        with self.assertRaisesRegex(ValueError, "未知消息 Channel"):
            normalize_channel_name("wechat")

    def test_console_prints_regular_message(self) -> None:
        message = StructuredMessage(
            title="plain text",
            blocks=[TextMessageBlock(text="hello")],
        )
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            delivery = send_message(message, "console")

        self.assertEqual(delivery.status, "PRINTED")
        self.assertIn("plain text", output.getvalue())


def worker_result(
    worker: str,
    status: WorkerStatus,
    *,
    rows_written: int = 0,
    error: WorkerError | None = None,
) -> WorkerResult:
    now = datetime.now(UTC)
    return WorkerResult(
        job_id="job-1",
        worker=worker,
        status=status,
        started_at=now,
        finished_at=now,
        duration_seconds=0,
        metrics={"rows_written": rows_written},
        attempts=[
            WorkerAttempt(
                number=1,
                status=status,
                started_at=now,
                finished_at=now,
                duration_seconds=0,
                rows_written=rows_written,
                executions=[],
                error=error,
            )
        ],
        error=error,
    )


if __name__ == "__main__":
    unittest.main()
