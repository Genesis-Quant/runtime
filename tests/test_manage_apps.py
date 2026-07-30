"""测试查询与回测管理命令。"""

from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from core.manage.apps import main


QUERY_ARGUMENTS = [
    "query",
    "--start-date",
    "2025-01-01",
    "--end-date",
    "2025-01-02",
    "--codes",
    '["000001.SZ"]',
    "--factors",
    '["close"]',
]

BACKTEST_ARGUMENTS = [
    "backtest",
    "--start-date",
    "2025-01-01",
    "--end-date",
    "2025-01-02",
    "--codes",
    '["000001.SZ"]',
    "--factors",
    '["close"]',
    "--callbacks",
    '{"initialize":"def initialize(mutable context) {}"}',
]


class FakeQueryResult:
    """提供 QueryResult 所需的最小上下文管理接口。"""

    def __init__(self, data: pd.DataFrame) -> None:
        self.data = data
        self.closed = False

    def __enter__(self) -> "FakeQueryResult":
        return self

    def __exit__(self, *args: object) -> bool:
        self.closed = True
        return False


class FakeBacktestResult:
    """提供 BacktestResult 所需的结果表和上下文管理接口。"""

    def __init__(self) -> None:
        self.closed = False
        self.trade_details = pd.DataFrame({"orderId": [1]})
        self.daily_positions = pd.DataFrame({"symbol": ["000001.XSHE"]})
        self.daily_portfolios = pd.DataFrame({"totalEquity": [100_000.0]})
        self.daily_trading_statistics = pd.DataFrame(
            {"todayBuyOpenTradeVolume": [100]}
        )

    def __enter__(self) -> "FakeBacktestResult":
        return self

    def __exit__(self, *args: object) -> bool:
        self.closed = True
        return False


class QueryCommandTests(unittest.TestCase):
    def test_output_is_required(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(QUERY_ARGUMENTS, prog="core-manage apps")

        self.assertEqual(raised.exception.code, 2)

    def test_query_writes_parquet_to_output(self) -> None:
        expected = pd.DataFrame(
            {
                "time": pd.to_datetime(["2025-01-02"]),
                "code": ["000001.SZ"],
                "close": [11.73],
            }
        )
        query_result = FakeQueryResult(expected)

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "nested"
            output = output_dir / "query.parquet"
            with patch(
                "core.apps.query.execute_query",
                return_value=query_result,
            ) as execute_query:
                exit_code = main(
                    [*QUERY_ARGUMENTS, "--output-dir", str(output_dir)],
                    prog="core-manage apps",
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(query_result.closed)
            self.assertTrue(output.is_file())
            pd.testing.assert_frame_equal(pd.read_parquet(output), expected)
            execute_query.assert_called_once_with(
                {
                    "start_date": "2025-01-01",
                    "end_date": "2025-01-02",
                    "codes": ["000001.SZ"],
                    "factors": ["close"],
                }
            )


class BacktestCommandTests(unittest.TestCase):
    def test_output_dir_is_required(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(BACKTEST_ARGUMENTS, prog="core-manage apps")

        self.assertEqual(raised.exception.code, 2)

    def test_backtest_writes_all_outputs_by_default(self) -> None:
        backtest_result = FakeBacktestResult()

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "backtest"
            with patch(
                "core.apps.backtest.run_backtest",
                return_value=backtest_result,
            ):
                exit_code = main(
                    [
                        *BACKTEST_ARGUMENTS,
                        "--output-dir",
                        str(output_dir),
                    ],
                    prog="core-manage apps",
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(backtest_result.closed)
            self.assertEqual(
                {path.name for path in output_dir.iterdir()},
                {
                    "trade_details.parquet",
                    "daily_positions.parquet",
                    "daily_portfolios.parquet",
                    "daily_trading_statistics.parquet",
                },
            )

    def test_backtest_writes_only_selected_outputs(self) -> None:
        backtest_result = FakeBacktestResult()

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "backtest"
            with patch(
                "core.apps.backtest.run_backtest",
                return_value=backtest_result,
            ):
                exit_code = main(
                    [
                        *BACKTEST_ARGUMENTS,
                        "--output-dir",
                        str(output_dir),
                        "--output",
                        '["trade_details","daily_portfolios"]',
                    ],
                    prog="core-manage apps",
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                {path.name for path in output_dir.iterdir()},
                {
                    "trade_details.parquet",
                    "daily_portfolios.parquet",
                },
            )

    def test_backtest_rejects_unknown_output(self) -> None:
        arguments = [
            *BACKTEST_ARGUMENTS,
            "--output-dir",
            "output",
            "--output",
            '["return_summary"]',
        ]
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(arguments, prog="core-manage apps")

        self.assertEqual(raised.exception.code, 2)

    def test_backtest_rejects_empty_output(self) -> None:
        arguments = [
            *BACKTEST_ARGUMENTS,
            "--output-dir",
            "output",
            "--output",
            "[]",
        ]
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(arguments, prog="core-manage apps")

        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
