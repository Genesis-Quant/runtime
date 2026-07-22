"""验证 Worker 运行日志包含可用于判断增量进度的关键信息。"""

from collections.abc import Iterable
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from core.workers.base import BaseWorker, DateWorker, StockWorker
from core.workers.base import date as date_worker_module
from core.workers.base import stock as stock_worker_module
from core.workers.base import worker as base_worker_module
from core.utils import paginate as paginate_module
from core.utils import retry as retry_module


class _BaseLogWorker(BaseWorker):
    """用于验证 BaseWorker 日志的最小具体实现。"""

    def __str__(self) -> str:
        return "<BaseLogWorker>"

    @property
    def factors(self) -> tuple[str, ...]:
        return ("sample",)

    def fetch_all(self) -> Iterable[pd.DataFrame]:
        return ()


class _StockLogWorker(StockWorker):
    """用于验证 StockWorker 日志的最小具体实现。"""

    def __str__(self) -> str:
        return "<StockLogWorker>"

    @property
    def factors(self) -> tuple[str, ...]:
        return ("sample",)

    def fetch_one(
            self,
            code: str,
            *,
            start_date: pd.Timestamp,
            end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        return self.EMPTY


class _DateLogWorker(DateWorker):
    """用于验证 DateWorker 日志的最小具体实现。"""

    def __str__(self) -> str:
        return "<DateLogWorker>"

    @property
    def factors(self) -> tuple[str, ...]:
        return ("sample",)

    def fetch_one(self, current_date: pd.Timestamp) -> pd.DataFrame:
        return self.EMPTY


def _logger_messages(logger: Mock, *levels: str) -> list[str]:
    """返回指定日志级别的消息正文，不依赖 Loguru sink 格式。"""
    messages: list[str] = []
    for level in levels:
        for call in getattr(logger, level).call_args_list:
            if not call.args:
                continue
            template = str(call.args[0])
            try:
                message = template.format(*call.args[1:], **call.kwargs)
            except (IndexError, KeyError, ValueError):
                message = " ".join(map(str, call.args))
            messages.append(message)
    return messages


def _joined_messages(logger: Mock, *levels: str) -> str:
    return "\n".join(_logger_messages(logger, *levels))


def _session(result: pd.DataFrame | None) -> SimpleNamespace:
    return SimpleNamespace(
        upload=Mock(),
        run=Mock(return_value=result),
        close=Mock(),
    )


def _result(code: str, current_date: str) -> pd.DataFrame:
    """构造符合 fetch_one 契约的单行结果。"""
    return pd.DataFrame(
        {
            "time": pd.to_datetime([current_date]),
            "code": [code],
            "factor": ["sample"],
            "value": pd.Series([1.0], dtype="float64"),
        }
    )


def test_stock_get_last_dates_logs_coverage_and_date_range(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _StockLogWorker(
        codes=["A", "B", "C"],
        start_date="20250101",
        end_date="20250131",
        throttle=0,
    )
    session = _session(
        pd.DataFrame(
            {
                "code": ["A", "B", "C"],
                "time": pd.to_datetime(
                    ["2025-01-02", "2025-01-05", None]
                ),
            }
        )
    )
    logger = Mock()
    monkeypatch.setattr(stock_worker_module, "create_session", lambda: session)
    monkeypatch.setattr(stock_worker_module, "logger", logger)

    dates = worker.get_last_dates()

    assert dates == {
        "A": pd.Timestamp("2025-01-02"),
        "B": pd.Timestamp("2025-01-05"),
    }
    session.close.assert_called_once_with()
    messages = _joined_messages(logger, "debug", "info")
    assert "2/3" in messages
    assert "1" in messages and ("缺失" in messages or "无历史" in messages)
    assert "2025-01-02" in messages
    assert "2025-01-05" in messages


def test_stock_get_last_dates_logs_full_update_when_history_is_empty(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _StockLogWorker(
        codes=["A", "B"],
        start_date="20250101",
        end_date="20250131",
        throttle=0,
    )
    session = _session(
        pd.DataFrame(
            {
                "code": pd.Series(dtype="object"),
                "time": pd.Series(dtype="datetime64[ns]"),
            }
        )
    )
    logger = Mock()
    monkeypatch.setattr(stock_worker_module, "create_session", lambda: session)
    monkeypatch.setattr(stock_worker_module, "logger", logger)

    assert worker.get_last_dates() == {}

    session.close.assert_called_once_with()
    messages = _joined_messages(logger, "debug", "info")
    assert "覆盖=0/2" in messages
    assert "缺失=2" in messages
    assert "最近数据日=无" in messages


def test_stock_fetch_all_logs_plan_and_completion_summary(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _StockLogWorker(
        codes=["A", "B", "C"],
        start_date="20250101",
        end_date="20250105",
        threads=1,
        throttle=0,
    )
    logger = Mock()
    monkeypatch.setattr(
        worker,
        "get_last_dates",
        lambda: {
            "A": pd.Timestamp("2025-01-01"),
            "B": pd.Timestamp("2025-01-05"),
        },
    )

    def fetch_one(
            code: str,
            *,
            start_date: pd.Timestamp,
            end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        assert end_date == pd.Timestamp("2025-01-05")
        if code == "A":
            assert start_date == pd.Timestamp("2025-01-02")
            return _result(code, "2025-01-02")
        assert code == "C"
        assert start_date == pd.Timestamp("2025-01-01")
        return worker.EMPTY

    monkeypatch.setattr(worker, "fetch_one", fetch_one)
    monkeypatch.setattr(stock_worker_module, "logger", logger)

    results = list(worker.fetch_all())

    assert len(results) == 2
    assert sum(map(len, results)) == 1
    info = _logger_messages(logger, "info")
    assert any(
        "增量计划" in message
        and "首次=1" in message
        and "续更=1" in message
        and "已最新=1" in message
        and "待请求=2/3" in message
        for message in info
    )
    summaries = [
        message
        for message in _logger_messages(logger, "debug", "info", "success")
        if "完成" in message or "汇总" in message
    ]
    assert any(
        "状态=完成" in message
        and "任务=2" in message
        and "非空=1" in message
        and "空=1" in message
        and "结果行=1" in message
        and "失败=0" in message
        for message in summaries
    )


@pytest.mark.parametrize(
    ("database_result", "expected", "markers"),
    [
        (
            pd.DataFrame({"time": pd.to_datetime(["2025-01-03 18:00"])}),
            pd.Timestamp("2025-01-03"),
            ("2025-01-03",),
        ),
        (
            pd.DataFrame({"time": pd.Series(dtype="datetime64[ns]")}),
            None,
            ("最近数据日=无",),
        ),
    ],
    ids=["history", "no-history"],
)
def test_date_get_last_date_logs_database_state(
        monkeypatch: pytest.MonkeyPatch,
        database_result: pd.DataFrame,
        expected: pd.Timestamp | None,
        markers: tuple[str, ...],
) -> None:
    worker = _DateLogWorker(
        start_date="20250101",
        end_date="20250105",
        throttle=0,
    )
    session = _session(database_result)
    logger = Mock()
    monkeypatch.setattr(date_worker_module, "create_session", lambda: session)
    monkeypatch.setattr(date_worker_module, "logger", logger)

    assert worker.get_last_date() == expected

    session.close.assert_called_once_with()
    messages = _joined_messages(logger, "debug", "info")
    for marker in markers:
        assert marker in messages


@pytest.mark.parametrize(
    ("last_date", "expected", "markers"),
    [
        (
            None,
            pd.date_range("2025-01-01", "2025-01-05"),
            ("全量", "5", "2025-01-01", "2025-01-05"),
        ),
        (
            pd.Timestamp("2025-01-02"),
            pd.date_range("2025-01-03", "2025-01-05"),
            ("增量", "3", "2025-01-03", "2025-01-05"),
        ),
        (
            pd.Timestamp("2025-01-05"),
            pd.DatetimeIndex([]),
            ("无需更新", "2025-01-05"),
        ),
    ],
    ids=["full", "incremental", "up-to-date"],
)
def test_pending_dates_logs_update_mode_and_effective_range(
        monkeypatch: pytest.MonkeyPatch,
        last_date: pd.Timestamp | None,
        expected: pd.DatetimeIndex,
        markers: tuple[str, ...],
) -> None:
    worker = _DateLogWorker(
        start_date="20250101",
        end_date="20250105",
        throttle=0,
    )
    logger = Mock()
    monkeypatch.setattr(worker, "get_last_date", lambda: last_date)
    monkeypatch.setattr(date_worker_module, "logger", logger)

    actual = worker.pending_dates()

    assert actual.equals(expected)
    messages = _joined_messages(logger, "debug", "info")
    for marker in markers:
        assert marker in messages


def test_paginator_logs_multiple_page_summary(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _BaseLogWorker(
        start_date="20250101",
        end_date="20250131",
        throttle=0,
        retry_interval=0,
    )
    logger = Mock()
    monkeypatch.setattr(paginate_module, "logger", logger)

    def endpoint(**params: object) -> pd.DataFrame:
        if params["offset"] == 0:
            return pd.DataFrame({"row": [1, 2]})
        return pd.DataFrame({"row": [3]})

    result = worker.paginator.fetch(
        endpoint,
        params={"ts_code": "A"},
        page_size=2,
        context="fina_indicator[A]",
        stop_on_short=True,
    )

    assert result["row"].tolist() == [1, 2, 3]
    messages = _logger_messages(logger, "debug", "info", "success")
    assert any(
        "fina_indicator[A]" in message
        and "有效页=2" in message
        and "原始行=3" in message
        and "补齐行=1" in message
        for message in messages
    )


def test_paginator_logs_and_aggregates_all_calls(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _BaseLogWorker(
        start_date="20250101",
        end_date="20250131",
        throttle=0,
    )
    logger = Mock()
    monkeypatch.setattr(paginate_module, "logger", logger)

    def endpoint(**params: object) -> pd.DataFrame:
        if params["offset"] == 0:
            return pd.DataFrame({"row": [1, 2]})
        return pd.DataFrame({"row": [3]})

    for number in range(12):
        worker.paginator.fetch(
            endpoint,
            params={"ts_code": f"S{number:02d}"},
            page_size=2,
            context=f"sample[S{number:02d}]",
            stop_on_short=True,
        )

    info_details = [
        message
        for message in _logger_messages(logger, "info")
        if "分页完成" in message
    ]
    assert len(info_details) == 12
    summary = worker.paginator.summary()
    assert "分页完成=12" in summary
    assert "多页=12" in summary
    assert "请求=24" in summary
    assert "有效页=24" in summary
    assert "返回行=36" in summary
    assert "补齐行=12" in summary


def test_retry_logs_recovery_after_a_transient_failure(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _BaseLogWorker(
        start_date="20250101",
        end_date="20250131",
        throttle=0,
        max_retries=2,
        retry_interval=0,
    )
    logger = Mock()
    monkeypatch.setattr(retry_module, "logger", logger)
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("temporary")
        return "ok"

    assert worker.retry(operation, context="sample[A]") == "ok"

    failures = _joined_messages(logger, "exception")
    assert "sample[A]" in failures
    assert "attempt=1/2" in failures
    recovered = _logger_messages(logger, "debug", "info", "success")
    assert any(
        "sample[A]" in message
        and "请求恢复" in message
        and "2/2" in message
        and "成功" in message
        for message in recovered
    )


def test_base_run_logs_unlimited_throttle_and_completion(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _BaseLogWorker(
        start_date="20250101",
        end_date="20250102",
        throttle=0,
    )
    logger = Mock()

    class Writer:
        def __enter__(self) -> "Writer":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        base_worker_module,
        "CoreTableWriter",
        lambda *args, **kwargs: Writer(),
    )
    monkeypatch.setattr(base_worker_module, "logger", logger)

    assert worker.run() == 0

    messages = _joined_messages(logger, "info", "success")
    assert "限速=不限速" in messages
    assert "更新完成" in messages
    assert "吞吐=" in messages


def test_base_run_reports_rows_written_before_a_later_batch_fails(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _BaseLogWorker(
        start_date="20250101",
        end_date="20250102",
        throttle=0,
        batch_size=2,
    )
    data = pd.DataFrame(
        {
            "time": pd.to_datetime(["2025-01-01"] * 3),
            "code": ["A", "B", "C"],
            "factor": ["sample"] * 3,
            "value": pd.Series([1.0, 2.0, 3.0], dtype="float64"),
        }
    )
    logger = Mock()

    class Writer:
        calls = 0

        def __enter__(self) -> "Writer":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def append(self, batch: pd.DataFrame) -> int:
            self.calls += 1
            if self.calls == 1:
                return len(batch)
            raise RuntimeError("second batch failed")

    monkeypatch.setattr(worker, "fetch_all", lambda: iter([data]))
    monkeypatch.setattr(
        base_worker_module,
        "CoreTableWriter",
        lambda *args, **kwargs: Writer(),
    )
    monkeypatch.setattr(base_worker_module, "logger", logger)
    with pytest.raises(RuntimeError, match="second batch failed"):
        worker.run()

    messages = _joined_messages(logger, "debug", "exception")
    assert "实际写入=2行" in messages
    assert "已确认写入=2行" in messages


def test_date_fetch_all_logs_completed_when_nothing_is_pending(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _DateLogWorker(
        start_date="20250101",
        end_date="20250102",
        throttle=0,
    )
    logger = Mock()
    monkeypatch.setattr(
        worker,
        "pending_dates",
        lambda: pd.DatetimeIndex([]),
    )
    monkeypatch.setattr(date_worker_module, "logger", logger)

    assert list(worker.fetch_all()) == []

    messages = _joined_messages(logger, "info")
    assert "获取汇总：状态=完成" in messages
    assert "日期=0/0" in messages


def test_date_fetch_all_logs_interrupted_generator(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _DateLogWorker(
        chunk_size=1,
        start_date="20250101",
        end_date="20250102",
        threads=1,
        throttle=0,
    )
    logger = Mock()
    monkeypatch.setattr(
        worker,
        "pending_dates",
        lambda: pd.date_range("2025-01-01", "2025-01-02"),
    )
    monkeypatch.setattr(date_worker_module, "logger", logger)

    results = worker.fetch_all()
    assert next(results).empty
    results.close()

    messages = _joined_messages(logger, "info")
    assert "获取汇总：状态=中止" in messages
    assert "日期=1/2" in messages


def test_stock_fetch_all_logs_interrupted_generator(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _StockLogWorker(
        codes=["A", "B"],
        start_date="20250101",
        end_date="20250102",
        threads=1,
        throttle=0,
    )
    logger = Mock()
    monkeypatch.setattr(worker, "get_last_dates", dict)
    monkeypatch.setattr(stock_worker_module, "logger", logger)

    results = worker.fetch_all()
    assert next(results).empty
    results.close()

    messages = _joined_messages(logger, "info")
    assert "获取汇总：状态=中止" in messages
    assert "任务=2" in messages


def test_date_fetch_all_caps_failure_samples_and_logs_failed_status(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = _DateLogWorker(
        chunk_size=20,
        start_date="20250101",
        end_date="20250112",
        threads=3,
        throttle=0,
    )
    logger = Mock()
    monkeypatch.setattr(
        worker,
        "pending_dates",
        lambda: pd.date_range("2025-01-01", "2025-01-12"),
    )
    monkeypatch.setattr(
        worker,
        "fetch_one",
        lambda current_date: (_ for _ in ()).throw(
            RuntimeError("failure " + "x" * 1_000)
        ),
    )
    monkeypatch.setattr(date_worker_module, "logger", logger)

    with pytest.raises(RuntimeError, match="共 12 个自然日") as caught:
        list(worker.fetch_all())

    item_errors = [
        message
        for message in _logger_messages(logger, "exception")
        if "获取失败" in message
    ]
    assert len(item_errors) == 12
    assert "x" * 1_000 in str(caught.value)
    assert "其余 2 条失败已省略" in str(caught.value)
    messages = _joined_messages(logger, "info")
    assert "获取汇总：状态=失败" in messages
    assert "失败=12" in messages


def test_stock_fetch_all_caps_failure_samples_and_logs_failed_status(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    codes = [f"S{number:02d}" for number in range(12)]
    worker = _StockLogWorker(
        codes=codes,
        start_date="20250101",
        end_date="20250102",
        threads=3,
        throttle=0,
    )
    logger = Mock()
    monkeypatch.setattr(worker, "get_last_dates", dict)

    def fail(
            code: str,
            *,
            start_date: pd.Timestamp,
            end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        raise RuntimeError(f"{code} failure " + "x" * 1_000)

    monkeypatch.setattr(worker, "fetch_one", fail)
    monkeypatch.setattr(stock_worker_module, "logger", logger)

    with pytest.raises(RuntimeError, match="共 12 只股票") as caught:
        list(worker.fetch_all())

    item_errors = [
        message
        for message in _logger_messages(logger, "exception")
        if "区间=" in message
    ]
    assert len(item_errors) == 12
    assert "x" * 1_000 in str(caught.value)
    assert "其余 2 条失败已省略" in str(caught.value)
    messages = _joined_messages(logger, "info")
    assert "获取汇总：状态=失败" in messages
    assert "失败=12" in messages
