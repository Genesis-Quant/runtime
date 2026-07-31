import json
from pathlib import Path
from typing import Any

import pandas as pd

import core.apps.backtest as backtest_package
import core.apps.query as query_package
from core.manage import apps as manage_apps


class FakeQueryResult:
    data = pd.DataFrame(
        {
            "time": pd.to_datetime(["2025-01-02"]),
            "code": ["000001.SZ"],
            "close": [10.0],
        }
    )

    def __enter__(self) -> "FakeQueryResult":
        return self

    def __exit__(self, *_: Any) -> None:
        return None


class FakeBacktestResult:
    trade_details = pd.DataFrame({"order_id": [1]})
    daily_positions = pd.DataFrame({"time": ["2025-01-02"]})
    daily_portfolios = pd.DataFrame({"net_value": [1.0]})
    daily_trading_statistics = pd.DataFrame({"trade_count": [1]})

    def __enter__(self) -> "FakeBacktestResult":
        return self

    def __exit__(self, *_: Any) -> None:
        return None


def write_input(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def test_manage_apps_registers_each_application_module() -> None:
    assert [application.NAME for application in manage_apps.APPLICATIONS] == [
        "query",
        "factor",
        "backtest",
    ]


def test_query_command_writes_fixed_output(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    input_file = write_input(
        tmp_path / "query.json",
        {
            "dataset_query": {"start_date": "2025-01-02"},
            "output_dir": "output",
        },
    )
    monkeypatch.setattr(
        query_package,
        "execute_query",
        lambda request: FakeQueryResult(),
    )

    assert manage_apps.main(
        ["query", "--input-file", str(input_file)]
    ) == 0
    output = tmp_path / "output" / "query.parquet"
    assert output.is_file()
    assert pd.read_parquet(output).columns.tolist() == [
        "time",
        "code",
        "close",
    ]


def test_backtest_command_writes_only_requested_outputs(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    input_file = write_input(
        tmp_path / "backtest.json",
        {
            "dataset_query": {"start_date": "2025-01-02"},
            "callbacks": {},
            "output_dir": "output",
            "output": ["trade_details", "daily_portfolios"],
        },
    )
    monkeypatch.setattr(
        backtest_package,
        "run_backtest",
        lambda **arguments: FakeBacktestResult(),
    )

    assert manage_apps.main(
        ["backtest", "--input-file", str(input_file)]
    ) == 0
    assert sorted(
        path.name for path in (tmp_path / "output").glob("*.parquet")
    ) == [
        "daily_portfolios.parquet",
        "trade_details.parquet",
    ]
