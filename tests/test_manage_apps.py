import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import core.apps.backtest as backtest_package
import core.apps.query as query_package
from core.manage import apps as manage_apps


class FakeQueryResult:
    def __init__(self) -> None:
        self.accessed: list[str] = []

    @property
    def data(self) -> pd.DataFrame:
        self.accessed.append("data")
        return pd.DataFrame({
            "time": pd.to_datetime(["2025-01-02"]),
            "code": ["000001.SZ"],
            "close": [10.0],
        })

    def __enter__(self) -> "FakeQueryResult":
        return self

    def __exit__(self, exception_type: Any, exception: Any, traceback: Any) -> None:
        return None


class FakeBacktestResult:
    def __init__(self) -> None:
        self.accessed: list[str] = []

    @property
    def trade_details(self) -> pd.DataFrame:
        self.accessed.append("trade_details")
        return pd.DataFrame({"order_id": [1]})

    @property
    def daily_portfolios(self) -> pd.DataFrame:
        self.accessed.append("daily_portfolios")
        return pd.DataFrame({"net_value": [1.0]})

    def __enter__(self) -> "FakeBacktestResult":
        return self

    def __exit__(self, exception_type: Any, exception: Any, traceback: Any) -> None:
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


@pytest.mark.parametrize("application", ["query", "factor", "backtest"])
def test_application_requires_output(tmp_path: Path, application: str) -> None:
    input_file = write_input(tmp_path / f"{application}.json", {})
    with pytest.raises(SystemExit) as error:
        manage_apps.main([application, "--input-file", str(input_file)])
    assert error.value.code == 2


def test_query_command_writes_only_requested_output(
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
    query_result = FakeQueryResult()
    monkeypatch.setattr(
        query_package,
        "execute_query",
        lambda request: query_result,
    )

    assert manage_apps.main(
        ["query", "--input-file", str(input_file), "--output", "data"]
    ) == 0
    output = tmp_path / "output" / "query.parquet"
    assert output.is_file()
    assert pd.read_parquet(output).columns.tolist() == [
        "time",
        "code",
        "close",
    ]
    assert query_result.accessed == ["data"]


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
        },
    )
    backtest_result = FakeBacktestResult()
    monkeypatch.setattr(
        backtest_package,
        "run_backtest",
        lambda **arguments: backtest_result,
    )

    assert manage_apps.main(
        [
            "backtest",
            "--input-file",
            str(input_file),
            "--output",
            "trade_details",
            "daily_portfolios",
        ]
    ) == 0
    assert sorted(
        path.name for path in (tmp_path / "output").glob("*.parquet")
    ) == [
        "daily_portfolios.parquet",
        "trade_details.parquet",
    ]
    assert backtest_result.accessed == ["trade_details", "daily_portfolios"]
