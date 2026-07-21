"""验证统一长表数据库层和数据工具的真实行为。"""

from dataclasses import dataclass
from datetime import date
import sys
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from core.database import session as database
from core.utils import dates, rate_limit, tushare


class FakeSession:
    """按回调返回结果并记录 DolphinDB 调用。"""

    def __init__(self, responder=None):
        self.responder = responder or (lambda script: None)
        self.scripts: list[str] = []
        self.uploads: list[dict[str, Any]] = []
        self.closed = False

    def connect(self, *args) -> bool:
        """记录连接参数并返回成功。"""
        self.connection = args
        return True

    def upload(self, values: dict[str, Any]) -> None:
        """记录上传变量。"""
        self.uploads.append(values)

    def run(self, script: str):
        """记录脚本并交给响应函数。"""
        self.scripts.append(script)
        return self.responder(script)

    def close(self) -> None:
        """记录会话关闭。"""
        self.closed = True


@pytest.mark.parametrize(
    ("index_code", "expected"),
    [
        ("000016.SH", "weight_000016SH"),
        (" 000300.sh ", "weight_000300SH"),
        ("399006.SZ", "weight_399006SZ"),
    ],
)
def test_index_weight_factor_normalizes_code(index_code: str, expected: str) -> None:
    """指数代码统一转大写并移除点号。"""
    assert database.index_weight_factor(index_code) == expected


@pytest.mark.parametrize(
    "index_code",
    [
        "",
        "   ",
        ".",
        ".SH",
        "000300.",
        "000300SH",
        "A..B",
        "000300-SH",
        "中证500",
    ],
)
def test_index_weight_factor_rejects_invalid_code(index_code: str) -> None:
    """空代码和含非法字符的代码不能成为分区名。"""
    with pytest.raises(ValueError, match="无效指数代码"):
        database.index_weight_factor(index_code)


def test_create_session_connects_with_config(monkeypatch) -> None:
    """库表已存在时使用集中配置连接，不再重复初始化。"""
    fake = FakeSession(lambda script: True)
    monkeypatch.setattr(database.dolphindb, "session", lambda: fake)
    assert database.create_session() is fake
    assert fake.connection == (
        database.DOLPHIN.HOST,
        database.DOLPHIN.PORT,
        database.DOLPHIN.USERNAME,
        database.DOLPHIN.PASSWORD,
    )
    assert not fake.uploads


@pytest.mark.parametrize(
    ("database_exists", "table_exists"),
    [(False, False), (True, False)],
)
def test_create_session_initializes_missing_core_table(
    monkeypatch,
    database_exists: bool,
    table_exists: bool,
) -> None:
    """数据库或统一表缺失时，首次连接自动执行幂等初始化。"""
    def respond(script: str):
        if script.startswith("existsDatabase"):
            return database_exists
        if script.startswith("existsTable"):
            return table_exists
        return None

    fake = FakeSession(respond)
    initialized: list[tuple[Any, list[str]]] = []
    monkeypatch.setattr(database.dolphindb, "session", lambda: fake)
    monkeypatch.setattr(
        database,
        "_initialize_with_session",
        lambda session, factors: initialized.append((session, factors)),
    )

    assert database.create_session() is fake
    assert initialized == [(fake, list(database.DEFAULT_FACTORS))]
    assert not fake.closed


def test_create_session_closes_when_schema_check_fails(monkeypatch) -> None:
    """库表检查或自动初始化异常时关闭刚建立的连接。"""
    def fail_check(script: str):
        raise RuntimeError("bad")

    fake = FakeSession(fail_check)
    monkeypatch.setattr(database.dolphindb, "session", lambda: fake)
    with pytest.raises(RuntimeError, match="bad"):
        database.create_session()
    assert fake.closed


def test_create_session_closes_failed_connection(monkeypatch) -> None:
    """connect 明确返回 false 时关闭对象并给出连接地址。"""
    fake = FakeSession()
    fake.connect = lambda *args: False
    monkeypatch.setattr(database.dolphindb, "session", lambda: fake)
    with pytest.raises(ConnectionError, match="无法连接 DolphinDB"):
        database.create_session()
    assert fake.closed


def test_initialize_database_uploads_schema_inputs_and_owns_session(monkeypatch) -> None:
    """显式初始化会清理 factors、执行建表脚本并关闭自建会话。"""
    fake = FakeSession(lambda script: "CoreData initialized")
    monkeypatch.setattr(database, "_connect_session", lambda: fake)
    result = database.initialize_database(
        ["close", " close ", "is_st", "  ", None]
    )
    assert result == "CoreData initialized"
    assert fake.closed
    uploaded = fake.uploads[0]
    assert uploaded["coreDatabaseName"] == database.DOLPHIN.DATABASE
    assert uploaded["coreTableName"] == database.DOLPHIN.TABLE
    assert uploaded["coreInitialFactors"].tolist() == ["close", "is_st"]
    assert "createPartitionedTable" in fake.scripts[0]


def test_initialize_database_uses_borrowed_session_and_rejects_empty() -> None:
    """借用会话不由函数关闭，空 factor 集合在连接前失败。"""
    fake = FakeSession(lambda script: "ok")
    assert database.initialize_database(["close"], session=fake) == "ok"
    assert not fake.closed
    with pytest.raises(ValueError, match="factor 至少"):
        database.initialize_database([], session=fake)


def test_ensure_factor_partitions_initializes_missing_database(monkeypatch) -> None:
    """数据库不存在时先初始化，再只添加 schema 中缺少的分区。"""
    def respond(script: str):
        if script.startswith("existsDatabase"):
            return False
        if script.startswith("schema(database"):
            return {"partitionSchema": [None, np.array(["close"])]}
        return "ok"

    fake = FakeSession(respond)
    initialized: list[list[str]] = []
    monkeypatch.setattr(
        database,
        "_initialize_with_session",
        lambda session, factors: initialized.append(factors) or "ok",
    )
    missing = database.ensure_factor_partitions(
        ["close", "is_st", "is_st"], session=fake
    )
    assert missing == ["is_st"]
    assert "is_st" in initialized[0]
    assert fake.uploads[-1]["coreNewFactorPartitions"].tolist() == ["is_st"]
    assert any("addValuePartitions" in script for script in fake.scripts)


def test_ensure_factor_partitions_returns_empty_and_closes_owned_session(monkeypatch) -> None:
    """分区全部存在时不执行 addValuePartitions，并关闭自建会话。"""
    fake = FakeSession(
        lambda script: True
        if script.startswith("existsDatabase")
        else {"partitionSchema": [None, np.array(["close", "is_st"])]}
    )
    monkeypatch.setattr(database, "create_session", lambda: fake)
    assert database.ensure_factor_partitions(["close", "is_st"]) == []
    assert fake.closed
    assert not any("addValuePartitions" in script for script in fake.scripts)


def test_normalize_core_frame_deduplicates_and_sorts() -> None:
    """统一写入按键保留最后值、转换类型并按 factor/code/time 排序。"""
    source = pd.DataFrame(
        {
            "time": ["2024-01-03", "2024-01-02", "2024-01-02"],
            "code": [" B ", "A", "A"],
            "factor": ["close", " close ", "close"],
            "value": [3, 1, 2],
            "ignored": [1, 2, 3],
        }
    )
    result = database.normalize_core_frame(source)
    assert list(result.columns) == list(database.CORE_COLUMNS)
    assert result[["code", "factor", "value"]].to_dict("records") == [
        {"code": "A", "factor": "close", "value": 2},
        {"code": "B", "factor": "close", "value": 3},
    ]


@pytest.mark.parametrize(
    "source",
    [
        {"not": "a dataframe"},
        pd.DataFrame({"time": ["2024-01-01"]}),
        pd.DataFrame(
            {"time": [None], "code": ["A"], "factor": ["x"], "value": [1]}
        ),
        pd.DataFrame(
            {"time": ["2024-01-01"], "code": [""], "factor": ["x"], "value": [1]}
        ),
        pd.DataFrame(
            {"time": ["2024-01-01"], "code": ["A"], "factor": [""], "value": [1]}
        ),
        pd.DataFrame(
            {"time": ["2024-01-01"], "code": ["A"], "factor": ["x"], "value": [np.inf]}
        ),
    ],
)
def test_normalize_core_frame_rejects_invalid_rows(source: object) -> None:
    """错误形态、缺列、空键、坏日期和非有限值都被拒绝。"""
    with pytest.raises((TypeError, ValueError)):
        database.normalize_core_frame(source)  # type: ignore[arg-type]


def test_normalize_core_frame_preserves_empty_contract() -> None:
    """带完整列的空输入返回同样的四列空表。"""
    empty = pd.DataFrame(columns=[*database.CORE_COLUMNS, "extra"])
    result = database.normalize_core_frame(empty)
    assert result.empty
    assert list(result.columns) == list(database.CORE_COLUMNS)


@dataclass
class WriterError:
    """模拟单行写入结果。"""

    failed: bool = False
    errorCode: str = "E1"
    errorInfo: str = "insert failed"

    def hasError(self) -> bool:
        """返回是否失败。"""
        return self.failed


@dataclass
class WriterStatus:
    """模拟多线程写入器最终状态。"""

    failed: bool = False
    unsentRows: int = 0
    sendFailedRows: int = 0
    errorCode: str = "E2"
    errorInfo: str = "writer failed"

    def hasError(self) -> bool:
        """返回是否失败。"""
        return self.failed


class FakeWriter:
    """记录写入行并可注入行级或最终错误。"""

    def __init__(self, *, insert_error_at=None, status=None, **kwargs):
        self.kwargs = kwargs
        self.rows: list[tuple[Any, ...]] = []
        self.insert_error_at = insert_error_at
        self.status = status or WriterStatus()
        self.waited = False

    def insert(self, *row) -> WriterError:
        """记录行并按序号返回错误。"""
        self.rows.append(row)
        return WriterError(len(self.rows) == self.insert_error_at)

    def waitForThreadCompletion(self) -> None:
        """记录等待调用。"""
        self.waited = True

    def getStatus(self) -> WriterStatus:
        """返回最终状态。"""
        return self.status


def _valid_long() -> pd.DataFrame:
    """构造两行合法统一长表。"""
    return pd.DataFrame(
        {
            "time": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "code": ["A", "B"],
            "factor": ["close", "close"],
            "value": [1.0, 2.0],
        }
    )


def test_write_core_table_writes_all_rows_and_checks_partitions(monkeypatch) -> None:
    """自动建库后的会话只补分区，随后等待写入线程完成。"""
    calls: list[tuple[list[str], Any]] = []
    session = FakeSession()
    writer = FakeWriter()
    monkeypatch.setattr(database, "create_session", lambda: session)
    monkeypatch.setattr(
        database,
        "ensure_factor_partitions",
        lambda factors, *, session: calls.append(
            (list(factors), session)
        ) or [],
    )
    monkeypatch.setattr(
        database.dolphindb,
        "MultithreadedTableWriter",
        lambda **kwargs: writer,
    )
    assert database.write_core_table(_valid_long()) == 2
    assert session.closed and len(writer.rows) == 2 and writer.waited
    assert calls == [(["close"], session)]


def test_write_core_table_returns_zero_for_empty() -> None:
    """空长表不连接数据库也不创建写入器。"""
    empty = pd.DataFrame(columns=database.CORE_COLUMNS)
    assert database.write_core_table(empty) == 0


@pytest.mark.parametrize(
    ("insert_error_at", "status", "message"),
    [
        (1, WriterStatus(), "DolphinDB 插入失败"),
        (None, WriterStatus(failed=True), "DolphinDB 批量写入失败"),
        (None, WriterStatus(unsentRows=1), "unsentRows=1"),
        (None, WriterStatus(sendFailedRows=2), "sendFailedRows=2"),
    ],
)
def test_write_core_table_propagates_writer_errors(
    monkeypatch,
    insert_error_at: int | None,
    status: WriterStatus,
    message: str,
) -> None:
    """行级错误、writer 错误、未发送和发送失败均不可静默忽略。"""
    session = FakeSession()
    writer = FakeWriter(insert_error_at=insert_error_at, status=status)
    monkeypatch.setattr(database, "create_session", lambda: session)
    monkeypatch.setattr(
        database,
        "ensure_factor_partitions",
        lambda factors, *, session: [],
    )
    monkeypatch.setattr(
        database.dolphindb,
        "MultithreadedTableWriter",
        lambda **kwargs: writer,
    )
    with pytest.raises(RuntimeError, match=message):
        database.write_core_table(_valid_long())
    assert writer.waited


def test_normalize_dates_supports_timezone_and_rejects_bad_ranges() -> None:
    """日期工具去除时区、归零，并明确拒绝坏值和倒置区间。"""
    value = dates.normalize_date("2024-01-02T12:30:00+08:00")
    assert value == pd.Timestamp("2024-01-02") and value.tzinfo is None
    assert dates.normalize_date_range("2024-01-01", "2024-01-02") == (
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2024-01-02"),
    )
    with pytest.raises(ValueError, match="不是有效日期"):
        dates.normalize_date("bad")
    with pytest.raises(ValueError, match="不是有效日期"):
        dates.normalize_date(pd.NaT)
    with pytest.raises(ValueError, match="不能晚于"):
        dates.normalize_date_range("2024-01-03", "2024-01-02")


def test_rate_limiter_validates_zero_and_waiting_paths(monkeypatch) -> None:
    """限流器拒绝负速率，零速率直返，耗尽令牌后等待再补充。"""
    with pytest.raises(ValueError, match="不能小于"):
        rate_limit.RateLimiter(-1)
    rate_limit.RateLimiter(0).acquire()

    moments = iter([0.0, 0.0, 1.0])
    sleeps: list[float] = []
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: next(moments))
    monkeypatch.setattr(rate_limit.time, "sleep", sleeps.append)
    limiter = rate_limit.RateLimiter(1)
    limiter.tokens = 0
    limiter.acquire()
    assert sleeps == [1.0]


def test_create_tushare_apis_are_lazy_and_validate_token(monkeypatch) -> None:
    """Pro API 和 pro_bar 均延迟导入并在创建前校验 token。"""
    for factory in (tushare.create_tushare_pro, tushare.create_tushare_pro_bar):
        with pytest.raises(RuntimeError, match="TUSHARE_TOKEN"):
            factory("")

    calls: list[tuple[str, str]] = []
    module = SimpleNamespace(
        set_token=lambda token: calls.append(("set", token)),
        pro_api=lambda token: calls.append(("pro", token)) or "PRO",
        pro_bar=lambda **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "tushare", module)
    assert tushare.create_tushare_pro("token") == "PRO"
    assert tushare.create_tushare_pro_bar("token") is module.pro_bar
    assert calls == [
        ("set", "token"),
        ("pro", "token"),
        ("set", "token"),
    ]


class CalendarClient:
    """按队列返回 trade_cal 响应。"""

    def __init__(self, responses: list[Any]):
        self.responses = responses
        self.calls = 0

    def trade_cal(self, **kwargs):
        """弹出响应或抛出异常。"""
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        self.kwargs = kwargs
        return response


def _calendar_frame() -> pd.DataFrame:
    """构造同时含字符串和整数 is_open 的交易日历。"""
    return pd.DataFrame(
        {
            "cal_date": ["20240101", "20240102", "20240103", "bad"],
            "is_open": ["0", "1", 1, 1],
        }
    )


def test_trading_calendar_retries_caches_and_filters(monkeypatch) -> None:
    """日历空响应后重试，手动判断 is_open，并在同一自然日复用缓存。"""
    monkeypatch.setattr(tushare.time, "sleep", lambda seconds: None)
    client = CalendarClient([pd.DataFrame(), _calendar_frame(), _calendar_frame()])
    calendar = tushare.TradingCalendar(
        client,
        start_date="2024-01-01",
        max_retries=2,
        retry_interval=0,
    )
    first = calendar.all(today=date(2024, 1, 3))
    second = calendar.all(today=date(2024, 1, 3))
    assert first.tolist() == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]
    assert second.equals(first) and client.calls == 2
    assert calendar.between(
        "2024-01-03", "2024-01-03", today=date(2024, 1, 3)
    ).tolist() == [pd.Timestamp("2024-01-03")]
    calendar.all(today=date(2024, 1, 4))
    assert client.calls == 3


def test_trading_calendar_rechecks_cache_after_acquiring_lock(monkeypatch) -> None:
    """并发调用等待锁期间若缓存已刷新，不再重复请求接口。"""
    calendar = tushare.TradingCalendar(CalendarClient([_calendar_frame()]))
    current = date(2024, 1, 3)
    cached = pd.DatetimeIndex([pd.Timestamp("2024-01-02")])

    class FillingLock:
        """模拟另一个线程在本线程取得锁前完成刷新。"""

        def __enter__(self):
            calendar._cache = cached
            calendar._cache_date = current

        def __exit__(self, *args):
            return False

    calendar._lock = FillingLock()
    monkeypatch.setattr(
        calendar,
        "_fetch",
        lambda today: pytest.fail("缓存已刷新时不应再次调用 _fetch"),
    )
    assert calendar.all(today=current).equals(cached)


@pytest.mark.parametrize(
    ("responses", "message"),
    [
        ([RuntimeError("down")], "获取交易日历失败"),
        ([pd.DataFrame({"cal_date": ["20240101"]})], "缺少列"),
        ([pd.DataFrame({"cal_date": ["20240101"], "is_open": [0]})], "没有开放交易日"),
    ],
)
def test_trading_calendar_reports_invalid_responses(
    monkeypatch,
    responses: list[Any],
    message: str,
) -> None:
    """持续异常、缺列和无开放日都给出最终错误。"""
    monkeypatch.setattr(tushare.time, "sleep", lambda seconds: None)
    calendar = tushare.TradingCalendar(
        CalendarClient(responses),
        max_retries=1,
        retry_interval=0,
    )
    with pytest.raises(RuntimeError, match=message):
        calendar.all(today=date(2024, 1, 1))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_date": "bad"},
        {"start_date": pd.NaT},
        {"max_retries": 0},
        {"retry_interval": -1},
    ],
)
def test_trading_calendar_rejects_invalid_retry_config(kwargs: dict[str, Any]) -> None:
    """日历起点、重试次数和等待时间均在请求接口前校验。"""
    with pytest.raises(ValueError):
        tushare.TradingCalendar(CalendarClient([_calendar_frame()]), **kwargs)
