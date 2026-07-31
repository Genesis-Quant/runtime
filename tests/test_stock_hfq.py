import pandas as pd
import pytest

from core.workers import stock_daily
from core.workers.stock_daily import StockHfqWorker


def make_worker() -> StockHfqWorker:
    return StockHfqWorker(
        codes=["000001.SZ"],
        start_date="2026-07-31",
        end_date="2026-07-31",
        throttle=0,
        max_retries=1,
    )


def test_stock_hfq_treats_tushare_generic_error_as_empty(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def raise_tushare_error(**_: str) -> pd.DataFrame:
        nonlocal calls
        calls += 1
        raise OSError("ERROR.")

    monkeypatch.setattr(stock_daily.ts, "pro_bar", raise_tushare_error)

    result = make_worker().fetch_one(
        "000001.SZ",
        start_date=pd.Timestamp("2026-07-31"),
        end_date=pd.Timestamp("2026-07-31"),
    )

    assert result is StockHfqWorker.EMPTY
    assert calls == 1


def test_stock_hfq_does_not_suppress_other_os_errors(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_other_error(**_: str) -> pd.DataFrame:
        raise OSError("connection failed")

    monkeypatch.setattr(stock_daily.ts, "pro_bar", raise_other_error)

    with pytest.raises(RuntimeError, match="connection failed"):
        make_worker().fetch_one(
            "000001.SZ",
            start_date=pd.Timestamp("2026-07-31"),
            end_date=pd.Timestamp("2026-07-31"),
        )
