"""验证 Worker 通用分页以及财务 Worker 的分页接入。"""

from collections.abc import Iterable
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from core.workers.base import BaseWorker
from core.workers import index_weight, stock_daily, stock_financial, stock_st
from core.workers.index_weight import IndexWeightWorker
from core.workers.stock_daily import (
    StockAdjFactorWorker,
    StockDailyBasicWorker,
    StockDailyWorker,
    StockHfqWorker,
)
from core.workers.stock_financial import (
    BALANCE_FACTORS,
    CASHFLOW_RAW_FACTORS,
    INCOME_RAW_FACTORS,
    INDICATOR_FACTORS,
    StockBalanceSheetWorker,
    StockCashflowWorker,
    StockFinaIndicatorWorker,
    StockIncomeWorker,
)
from core.workers.stock_st import StockSTWorker


class _CountingLimiter:
    """记录 acquire 次数，避免测试依赖真实时间。"""

    def __init__(self) -> None:
        self.calls = 0

    def acquire(self) -> None:
        self.calls += 1


class _Worker(BaseWorker):
    """只用于测试 BaseWorker 具体方法的最小实现。"""

    def __str__(self) -> str:
        return "<_Worker>"

    @property
    def factors(self) -> tuple[str, ...]:
        return ("sample",)

    def fetch_all(self) -> Iterable[pd.DataFrame]:
        return ()


def _worker(*, max_retries: int = 3) -> _Worker:
    worker = _Worker(
        start_date="20250101",
        end_date="20251231",
        throttle=0,
        max_retries=max_retries,
        retry_interval=0,
    )
    worker.limiter = _CountingLimiter()
    return worker


def test_paginator_reads_exact_full_pages_until_empty() -> None:
    """恰好整页不是结束信号，应继续请求并在空页结束。"""
    worker = _worker()
    calls: list[dict[str, object]] = []

    def endpoint(**params: object) -> pd.DataFrame:
        calls.append(params)
        offset = int(params["offset"])
        pages = {
            0: pd.DataFrame({"row": [1, 2]}),
            2: pd.DataFrame({"row": [3, 4]}),
            4: pd.DataFrame({"row": pd.Series(dtype="int64")}),
        }
        return pages[offset]

    result = worker.paginator.fetch(
        endpoint,
        params={"ts_code": "000001.SZ"},
        page_size=2,
        context="test endpoint",
        stop_on_short=True,
    )

    assert result.to_dict("list") == {"row": [1, 2, 3, 4]}
    assert calls == [
        {"ts_code": "000001.SZ", "limit": 2, "offset": 0},
        {"ts_code": "000001.SZ", "limit": 2, "offset": 2},
        {"ts_code": "000001.SZ", "limit": 2, "offset": 4},
    ]
    assert worker.limiter.calls == 3


def test_paginator_advances_by_actual_length_without_short_stop() -> None:
    """服务端静默缩小页长时，offset 应按实际返回行数前进。"""
    worker = _worker()
    offsets: list[int] = []

    def endpoint(**params: object) -> pd.DataFrame:
        offset = int(params["offset"])
        offsets.append(offset)
        if offset < 2:
            return pd.DataFrame({"row": [offset]})
        return pd.DataFrame({"row": pd.Series(dtype="int64")})

    result = worker.paginator.fetch(
        endpoint,
        params={},
        page_size=100,
        context="clamped endpoint",
    )

    assert result["row"].tolist() == [0, 1]
    assert offsets == [0, 1, 2]
    assert worker.limiter.calls == 3


def test_paginator_retries_only_the_failed_page() -> None:
    """单页失败只重试当前 offset，成功的上一页不应重新获取。"""
    worker = _worker(max_retries=2)
    offsets: list[int] = []
    failed_once = False

    def endpoint(**params: object) -> pd.DataFrame:
        nonlocal failed_once
        offset = int(params["offset"])
        offsets.append(offset)
        if offset == 0:
            return pd.DataFrame({"row": [1, 2]})
        if not failed_once:
            failed_once = True
            raise ConnectionError("temporary failure")
        return pd.DataFrame({"row": [3]})

    result = worker.paginator.fetch(
        endpoint,
        params={},
        page_size=2,
        context="unstable endpoint",
        stop_on_short=True,
    )

    assert result["row"].tolist() == [1, 2, 3]
    assert offsets == [0, 2, 2]
    assert worker.limiter.calls == 3


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"page_size": 0}, "page_size 必须大于 0"),
        ({"max_pages": 0}, "max_pages 必须大于 0"),
        ({"params": {"limit": 1}}, "params 不能包含 limit 或 offset"),
        ({"params": {"offset": 0}}, "params 不能包含 limit 或 offset"),
    ],
)
def test_paginator_rejects_invalid_configuration(
        arguments: dict[str, object],
        message: str,
) -> None:
    worker = _worker()
    kwargs: dict[str, object] = {
        "params": {},
        "page_size": 1,
        "context": "invalid endpoint",
    }
    kwargs.update(arguments)

    with pytest.raises(ValueError, match=message):
        worker.paginator.fetch(lambda **_: pd.DataFrame(), **kwargs)

    assert worker.limiter.calls == 0


def test_paginator_retries_and_rejects_non_dataframe() -> None:
    worker = _worker(max_retries=2)

    with pytest.raises(RuntimeError, match="共尝试 2 次") as caught:
        worker.paginator.fetch(
            lambda **_: None,
            params={},
            page_size=1,
            context="bad endpoint",
        )

    assert isinstance(caught.value.__cause__, TypeError)
    assert "分页响应不是 DataFrame" in str(caught.value.__cause__)
    assert worker.limiter.calls == 2


def test_paginator_preserves_an_empty_first_page_schema() -> None:
    worker = _worker()
    empty = pd.DataFrame({"row": pd.Series(dtype="int64")})

    result = worker.paginator.fetch(
        lambda **_: empty,
        params={},
        page_size=10,
        context="empty endpoint",
    )

    assert result is empty
    assert result.dtypes.to_dict() == empty.dtypes.to_dict()
    assert worker.limiter.calls == 1


def test_paginator_rejects_schema_changes_between_pages() -> None:
    worker = _worker()

    def endpoint(**params: object) -> pd.DataFrame:
        if params["offset"] == 0:
            return pd.DataFrame({"row": [1, 2]})
        return pd.DataFrame({"changed": [3]})

    with pytest.raises(ValueError, match="第 2 页字段发生变化"):
        worker.paginator.fetch(
            endpoint,
            params={},
            page_size=2,
            context="changing endpoint",
            stop_on_short=True,
        )

    assert worker.limiter.calls == 2


def test_paginator_rejects_a_repeated_page_ignoring_row_order() -> None:
    worker = _worker()

    def endpoint(**params: object) -> pd.DataFrame:
        if params["offset"] == 0:
            return pd.DataFrame({"row": [1, 2]})
        return pd.DataFrame({"row": [2, 1]})

    with pytest.raises(RuntimeError, match="第 2 页内容重复"):
        worker.paginator.fetch(
            endpoint,
            params={},
            page_size=2,
            context="repeating endpoint",
        )

    assert worker.limiter.calls == 2


def test_paginator_fails_closed_at_max_pages() -> None:
    worker = _worker()

    def endpoint(**params: object) -> pd.DataFrame:
        offset = int(params["offset"])
        return pd.DataFrame({"row": [offset, offset + 1]})

    with pytest.raises(RuntimeError, match="已达到最大分页数 2"):
        worker.paginator.fetch(
            endpoint,
            params={},
            page_size=2,
            context="endless endpoint",
            max_pages=2,
        )

    assert worker.limiter.calls == 2


def _financial_response(
        *,
        ann_date_col: str,
        factors: tuple[str, ...],
        populated_factor: str,
) -> pd.DataFrame:
    """创建按公告日倒序的 101 个季度，模拟恰好一页再加一行。"""
    end_dates = pd.date_range("2000-03-31", periods=101, freq="QE-DEC")
    values: dict[str, object] = {
        "end_date": end_dates.strftime("%Y%m%d"),
        ann_date_col: (end_dates + pd.offsets.Day(30)).strftime("%Y%m%d"),
        **{factor: np.full(len(end_dates), np.nan) for factor in factors},
    }
    values[populated_factor] = np.arange(1, len(end_dates) + 1, dtype=float)
    return (
        pd.DataFrame(values)
        .sort_values(ann_date_col, ascending=False)
        .reset_index(drop=True)
    )


@pytest.mark.parametrize(
    (
        "worker_type",
        "endpoint_name",
        "ann_date_col",
        "factors",
        "populated_factor",
    ),
    [
        (
            StockBalanceSheetWorker,
            "balancesheet",
            "f_ann_date",
            BALANCE_FACTORS,
            "total_assets",
        ),
        (
            StockFinaIndicatorWorker,
            "fina_indicator",
            "ann_date",
            INDICATOR_FACTORS,
            "eps",
        ),
    ],
    ids=["balance-sheet", "financial-indicator"],
)
def test_financial_fetch_one_reads_all_pages_and_returns_normalized_data(
        monkeypatch: pytest.MonkeyPatch,
        worker_type: type[StockBalanceSheetWorker | StockFinaIndicatorWorker],
        endpoint_name: str,
        ann_date_col: str,
        factors: tuple[str, ...],
        populated_factor: str,
) -> None:
    raw = _financial_response(
        ann_date_col=ann_date_col,
        factors=factors,
        populated_factor=populated_factor,
    )
    calls: list[dict[str, object]] = []

    def endpoint(**params: object) -> pd.DataFrame:
        calls.append(params)
        offset = int(params["offset"])
        limit = int(params["limit"])
        return raw.iloc[offset:offset + limit].copy()

    monkeypatch.setattr(
        stock_financial,
        "pro",
        SimpleNamespace(**{endpoint_name: endpoint}),
    )
    worker = worker_type(
        codes=["000001.SZ"],
        start_date="20000101",
        end_date="20251231",
        throttle=0,
        max_retries=2,
        retry_interval=0,
    )
    worker.limiter = _CountingLimiter()

    result = worker.fetch_one(
        "000001.SZ",
        start_date=pd.Timestamp("2000-01-01"),
        end_date=pd.Timestamp("2025-12-31"),
    )

    assert tuple(result.columns) == worker.COLUMNS
    assert pd.api.types.is_datetime64_any_dtype(result["time"])
    assert pd.api.types.is_float_dtype(result["value"])
    assert len(result) == 101
    assert result["code"].unique().tolist() == ["000001.SZ"]
    assert result["factor"].unique().tolist() == [populated_factor]
    assert result["value"].tolist() == pytest.approx(list(range(1, 102)))
    assert [(call["offset"], call["limit"]) for call in calls] == [
        (0, 100),
        (100, 100),
    ]
    assert all(call["ts_code"] == "000001.SZ" for call in calls)
    assert all(call["start_date"] == "19990101" for call in calls)
    assert all(call["end_date"] == "20251231" for call in calls)
    assert worker.limiter.calls == 2


@pytest.mark.parametrize(
    ("worker_type", "endpoint_name"),
    [
        (StockDailyWorker, "daily"),
        (StockDailyBasicWorker, "daily_basic"),
        (StockAdjFactorWorker, "adj_factor"),
    ],
    ids=["daily", "daily-basic", "adj-factor"],
)
def test_date_market_fetch_one_uses_one_limited_request_and_normalizes(
        monkeypatch: pytest.MonkeyPatch,
        worker_type: type[
            StockDailyWorker | StockDailyBasicWorker | StockAdjFactorWorker
        ],
        endpoint_name: str,
) -> None:
    worker = worker_type(
        start_date="20250102",
        end_date="20250102",
        throttle=0,
        retry_interval=0,
    )
    worker.limiter = _CountingLimiter()
    calls: list[dict[str, object]] = []
    response = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"],
            "trade_date": ["20250102"],
            **{
                factor: [float(index)]
                for index, factor in enumerate(worker.factors, start=1)
            },
        }
    )

    def endpoint(**params: object) -> pd.DataFrame:
        calls.append(params)
        return response.copy()

    monkeypatch.setattr(
        stock_daily,
        "pro",
        SimpleNamespace(**{endpoint_name: endpoint}),
    )

    result = worker.fetch_one(pd.Timestamp("2025-01-02"))

    assert tuple(result.columns) == worker.COLUMNS
    assert len(result) == len(worker.factors)
    assert result["code"].unique().tolist() == ["000001.SZ"]
    assert set(result["factor"]) == set(worker.factors)
    assert result["time"].unique().tolist() == [pd.Timestamp("2025-01-02")]
    assert calls == [
        {
            "trade_date": "20250102",
            "fields": ",".join(("ts_code", "trade_date", *worker.factors)),
        }
    ]
    assert worker.limiter.calls == 1


def test_hfq_fetch_one_uses_one_limited_request_and_renames_factors(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def pro_bar(**params: object) -> pd.DataFrame:
        calls.append(params)
        return pd.DataFrame(
            {
                "trade_date": ["20250102", "20250103"],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "change": [1.0, 1.0],
                "pct_chg": [10.0, 9.09],
            }
        )

    monkeypatch.setattr(stock_daily, "ts", SimpleNamespace(pro_bar=pro_bar))
    worker = StockHfqWorker(
        codes=["000001.SZ"],
        start_date="20250102",
        end_date="20250103",
        throttle=0,
        retry_interval=0,
    )
    worker.limiter = _CountingLimiter()

    result = worker.fetch_one(
        "000001.SZ",
        start_date=pd.Timestamp("2025-01-02"),
        end_date=pd.Timestamp("2025-01-03"),
    )

    assert tuple(result.columns) == worker.COLUMNS
    assert len(result) == 2 * len(worker.factors)
    assert set(result["factor"]) == set(worker.factors)
    assert result["code"].unique().tolist() == ["000001.SZ"]
    assert calls == [
        {
            "ts_code": "000001.SZ",
            "adj": "hfq",
            "start_date": "20250102",
            "end_date": "20250103",
        }
    ]
    assert worker.limiter.calls == 1


def test_stock_st_fetch_one_uses_one_limited_request_and_sets_sparse_value(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def endpoint(**params: object) -> pd.DataFrame:
        calls.append(params)
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "600000.SH"],
                "trade_date": ["20250102", "20250102"],
            }
        )

    monkeypatch.setattr(
        stock_st,
        "pro",
        SimpleNamespace(stock_st=endpoint),
    )
    worker = StockSTWorker(
        start_date="20250102",
        end_date="20250102",
        throttle=0,
        retry_interval=0,
    )
    worker.limiter = _CountingLimiter()

    result = worker.fetch_one(pd.Timestamp("2025-01-02"))

    assert tuple(result.columns) == worker.COLUMNS
    assert len(result) == 2
    assert set(result["code"]) == {"000001.SZ", "600000.SH"}
    assert result["factor"].unique().tolist() == list(worker.factors)
    assert result["value"].tolist() == [1.0, 1.0]
    assert calls == [
        {"trade_date": "20250102", "fields": "ts_code,trade_date"}
    ]
    assert worker.limiter.calls == 1


def test_index_weight_fetch_one_uses_latest_snapshot_and_current_time(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def endpoint(**params: object) -> pd.DataFrame:
        calls.append(params)
        return pd.DataFrame(
            {
                "trade_date": ["20241129", "20241231", "20241231"],
                "con_code": ["000003.SZ", "000001.SZ", "000002.SZ"],
                "weight": [9.0, 4.0, 6.0],
            }
        )

    monkeypatch.setattr(
        index_weight,
        "pro",
        SimpleNamespace(index_weight=endpoint),
    )
    worker = IndexWeightWorker(
        "000300.SH",
        start_date="20250110",
        end_date="20250110",
        throttle=0,
        retry_interval=0,
    )
    worker.limiter = _CountingLimiter()

    result = worker.fetch_one(pd.Timestamp("2025-01-10"))

    assert tuple(result.columns) == worker.COLUMNS
    assert len(result) == 2
    assert set(result["code"]) == {"000001.SZ", "000002.SZ"}
    assert result["factor"].unique().tolist() == list(worker.factors)
    assert result["time"].unique().tolist() == [pd.Timestamp("2025-01-10")]
    assert sorted(result["value"].tolist()) == [4.0, 6.0]
    assert calls == [
        {"index_code": "000300.SH", "end_date": "20250110"}
    ]
    assert worker.limiter.calls == 1


@pytest.mark.parametrize(
    ("worker_type", "endpoint_name", "raw_factors", "populated_factor"),
    [
        (
            StockIncomeWorker,
            "income",
            INCOME_RAW_FACTORS,
            "revenue",
        ),
        (
            StockCashflowWorker,
            "cashflow",
            CASHFLOW_RAW_FACTORS,
            "n_cashflow_act",
        ),
    ],
    ids=["income", "cashflow"],
)
def test_flow_financial_fetch_one_paginates_and_returns_derived_factors(
        monkeypatch: pytest.MonkeyPatch,
        worker_type: type[StockIncomeWorker | StockCashflowWorker],
        endpoint_name: str,
        raw_factors: tuple[str, ...],
        populated_factor: str,
) -> None:
    raw = _financial_response(
        ann_date_col="f_ann_date",
        factors=raw_factors,
        populated_factor=populated_factor,
    )
    calls: list[dict[str, object]] = []

    def endpoint(**params: object) -> pd.DataFrame:
        calls.append(params)
        offset = int(params["offset"])
        limit = int(params["limit"])
        return raw.iloc[offset:offset + limit].copy()

    monkeypatch.setattr(
        stock_financial,
        "pro",
        SimpleNamespace(**{endpoint_name: endpoint}),
    )
    worker = worker_type(
        codes=["000001.SZ"],
        start_date="20000101",
        end_date="20251231",
        throttle=0,
        retry_interval=0,
    )
    worker.limiter = _CountingLimiter()

    result = worker.fetch_one(
        "000001.SZ",
        start_date=pd.Timestamp("2000-01-01"),
        end_date=pd.Timestamp("2025-12-31"),
    )

    expected_factors = {
        f"{populated_factor}_{suffix}"
        for suffix in ("ttm", "1", "2", "3", "4")
    }
    assert tuple(result.columns) == worker.COLUMNS
    assert not result.empty
    assert set(result["factor"]) == expected_factors
    assert result["code"].unique().tolist() == ["000001.SZ"]
    assert np.isfinite(result["value"]).all()
    assert [(call["offset"], call["limit"]) for call in calls] == [
        (0, 100),
        (100, 100),
    ]
    assert all(call["ts_code"] == "000001.SZ" for call in calls)
    assert all(call["start_date"] == "19980101" for call in calls)
    assert all(call["end_date"] == "20251231" for call in calls)
    assert worker.limiter.calls == 2


def test_stock_fetch_all_does_not_add_an_outer_limiter_acquire(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_calls: list[str] = []

    def pro_bar(**params: object) -> pd.DataFrame:
        code = str(params["ts_code"])
        api_calls.append(code)
        return pd.DataFrame(
            {
                "trade_date": ["20250102"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.0],
                "close": [10.5],
                "change": [0.5],
                "pct_chg": [5.0],
            }
        )

    monkeypatch.setattr(stock_daily, "ts", SimpleNamespace(pro_bar=pro_bar))
    worker = StockHfqWorker(
        codes=["000001.SZ", "000002.SZ"],
        start_date="20250102",
        end_date="20250102",
        threads=1,
        throttle=0,
        retry_interval=0,
    )
    monkeypatch.setattr(worker, "get_last_dates", lambda: {})
    worker.limiter = _CountingLimiter()

    results = list(worker.fetch_all())

    assert len(results) == 2
    assert sum(map(len, results)) == 2 * len(worker.factors)
    assert api_calls == ["000001.SZ", "000002.SZ"]
    assert worker.limiter.calls == len(api_calls) == 2


def test_date_fetch_all_does_not_add_an_outer_limiter_acquire(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_calls: list[str] = []

    def endpoint(**params: object) -> pd.DataFrame:
        trade_date = str(params["trade_date"])
        api_calls.append(trade_date)
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": [trade_date],
                "adj_factor": [1.0],
            }
        )

    monkeypatch.setattr(
        stock_daily,
        "pro",
        SimpleNamespace(adj_factor=endpoint),
    )
    worker = StockAdjFactorWorker(
        start_date="20250102",
        end_date="20250103",
        threads=1,
        throttle=0,
        retry_interval=0,
        chunk_size=2,
    )
    monkeypatch.setattr(
        worker,
        "pending_dates",
        lambda: pd.DatetimeIndex(["2025-01-02", "2025-01-03"]),
    )
    worker.limiter = _CountingLimiter()

    results = list(worker.fetch_all())

    assert len(results) == 1
    assert len(results[0]) == 2
    assert api_calls == ["20250102", "20250103"]
    assert worker.limiter.calls == len(api_calls) == 2
