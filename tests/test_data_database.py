"""验证统一长表数据库层和数据工具的真实行为。"""

from typing import Any

import numpy as np
import pandas as pd
import pytest

from core.database import session as database
from core.utils import dates, schema, throttle, ts_api


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
    assert schema.index_weight_factor(index_code) == expected


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
        schema.index_weight_factor(index_code)


def test_create_session_connects_with_config(monkeypatch) -> None:
    """使用集中配置连接，不检查或初始化业务库表。"""
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
    assert not fake.scripts


def test_create_session_closes_failed_connection(monkeypatch) -> None:
    """connect 明确返回 false 时关闭对象并给出连接地址。"""
    fake = FakeSession()
    fake.connect = lambda *args: False
    monkeypatch.setattr(database.dolphindb, "session", lambda: fake)
    with pytest.raises(ConnectionError, match="无法连接 DolphinDB"):
        database.create_session()
    assert fake.closed


def test_ensure_factor_partitions_initializes_missing_database() -> None:
    """数据库不存在时先初始化，再只添加 schema 中缺少的分区。"""
    def respond(script: str):
        if script.startswith("existsDatabase"):
            return False
        if script.startswith("schema(database"):
            return {"partitionSchema": [None, np.array(["close"])]}
        return "ok"

    fake = FakeSession(respond)
    missing = database.ensure_factor_partitions(
        ["close", "is_st", "is_st"], session=fake
    )
    assert missing == ["is_st"]
    assert fake.uploads[0]["coreInitialFactors"].tolist() == ["close", "is_st"]
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
        throttle.RateLimiter(-1)
    throttle.RateLimiter(0).acquire()

    moments = iter([0.0, 0.0, 1.0])
    sleeps: list[float] = []
    monkeypatch.setattr(throttle.time, "monotonic", lambda: next(moments))
    monkeypatch.setattr(throttle.time, "sleep", sleeps.append)
    limiter = throttle.RateLimiter(1)
    limiter.tokens = 0
    limiter.acquire()
    assert sleeps == [1.0]


class CalendarClient:
    """返回预设的 trade_cal 响应并记录请求参数。"""

    def __init__(self, response: Any):
        self.response = response
        self.kwargs: dict[str, Any] = {}

    def trade_cal(self, **kwargs):
        """记录参数并返回预设响应。"""
        self.kwargs = kwargs
        return self.response


def _calendar_frame() -> pd.DataFrame:
    """构造同时含字符串和整数 is_open 的交易日历。"""
    return pd.DataFrame(
        {
            "cal_date": ["20240103", "20240101", "20240102", "20240102"],
            "is_open": [1, "0", "1", 1],
        }
    )


def test_get_trading_dates_filters_sorts_and_deduplicates(monkeypatch) -> None:
    """交易日历只保留开放日，并按日期排序去重。"""
    client = CalendarClient(_calendar_frame())
    monkeypatch.setattr(ts_api, "pro", client)
    result = ts_api.get_trading_dates("2024-01-01", "2024-01-03")
    assert result.tolist() == [
        pd.Timestamp("2024-01-02"),
        pd.Timestamp("2024-01-03"),
    ]
    assert client.kwargs == {
        "exchange": "SSE",
        "start_date": "20240101",
        "end_date": "20240103",
        "is_open": "1",
        "fields": "cal_date,is_open",
    }


@pytest.mark.parametrize(
    ("response", "error", "message"),
    [
        (None, RuntimeError, "返回 None"),
        ([], TypeError, "必须是 DataFrame"),
        (pd.DataFrame({"cal_date": ["20240101"]}), ValueError, "缺少列"),
        (
            pd.DataFrame({"cal_date": ["20240101"], "is_open": ["bad"]}),
            ValueError,
            "无效 is_open",
        ),
        (
            pd.DataFrame({"cal_date": ["bad"], "is_open": [1]}),
            ValueError,
            "无效 cal_date",
        ),
    ],
)
def test_get_trading_dates_rejects_invalid_responses(
    monkeypatch,
    response: Any,
    error: type[Exception],
    message: str,
) -> None:
    """异常响应不会被静默转换为空日历。"""
    monkeypatch.setattr(ts_api, "pro", CalendarClient(response))
    with pytest.raises(error, match=message):
        ts_api.get_trading_dates("2024-01-01", "2024-01-03")


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (pd.DataFrame(columns=["cal_date", "is_open"]), []),
        (
            pd.DataFrame({"cal_date": ["20240101"], "is_open": [0]}),
            [],
        ),
    ],
)
def test_get_trading_dates_allows_empty_ranges(
        monkeypatch,
        response: pd.DataFrame,
        expected: list[pd.Timestamp],
) -> None:
    """无交易日的合法区间返回空 DatetimeIndex。"""
    monkeypatch.setattr(ts_api, "pro", CalendarClient(response))
    result = ts_api.get_trading_dates("2024-01-01", "2024-01-01")
    assert isinstance(result, pd.DatetimeIndex)
    assert result.tolist() == expected
