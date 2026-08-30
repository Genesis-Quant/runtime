import unittest
from unittest.mock import Mock, call

import pandas as pd

from runtime.apps.backtest.result import BacktestResult


class BacktestResultTests(unittest.TestCase):
    def test_daily_positions_corrects_sell_fields_without_changing_buys(self) -> None:
        positions = pd.DataFrame(
            {
                "symbol": ["000001.XSHE", "000001.XSHE", "600000.XSHG"],
                "tradeDate": pd.to_datetime(
                    ["2026-01-05", "2026-01-06", "2026-01-06"]
                ),
                "todayBuyVolume": [200, 0, 0],
                "todayBuyValue": [2000.0, 0.0, 0.0],
                "todaySellVolume": [0, 0, 0],
                "todaySellValue": [0.0, 0.0, 0.0],
            }
        )
        statistics = pd.DataFrame(
            {
                "symbol": ["000001.XSHE", "600000.XSHG"],
                "tradeDate": pd.to_datetime(["2026-01-06", "2026-01-06"]),
                "todaySellOpenTradeVolume": [0, 50],
                "todaySellOpenTradeValue": [0.0, 500.0],
                "todaySellCloseTradeVolume": [100, 20],
                "todaySellCloseTradeValue": [1250.0, 220.0],
            }
        )
        session = Mock()
        session.run.side_effect = [positions, statistics]

        backtest_result = BacktestResult(session=session)
        result = backtest_result.daily_positions

        self.assertEqual(result["todayBuyVolume"].tolist(), [200, 0, 0])
        self.assertEqual(result["todayBuyValue"].tolist(), [2000.0, 0.0, 0.0])
        self.assertEqual(result["todaySellVolume"].tolist(), [0, 100, 70])
        self.assertEqual(result["todaySellValue"].tolist(), [0.0, 1250.0, 720.0])
        self.assertEqual(
            result["todaySellVolume"].dtype,
            positions["todaySellVolume"].dtype,
        )
        self.assertEqual(
            result["todaySellValue"].dtype,
            positions["todaySellValue"].dtype,
        )
        self.assertEqual(positions["todaySellVolume"].tolist(), [0, 0, 0])
        self.assertEqual(
            session.run.call_args_list,
            [
                call("Backtest::getDailyPosition(coreBacktestEngine)"),
                call("Backtest::getDailyTradingStatistics(coreBacktestEngine)"),
            ],
        )
        self.assertIs(backtest_result.daily_trading_statistics, statistics)
        self.assertEqual(len(session.run.call_args_list), 2)

    def test_statistics_loaded_first_are_reused_by_daily_positions(self) -> None:
        positions = pd.DataFrame(
            {
                "symbol": ["000001.XSHE"],
                "tradeDate": pd.to_datetime(["2026-01-06"]),
                "todaySellVolume": [0],
                "todaySellValue": [0.0],
            }
        )
        statistics = pd.DataFrame(
            {
                "symbol": ["000001.XSHE"],
                "tradeDate": pd.to_datetime(["2026-01-06"]),
                "todaySellOpenTradeVolume": [0],
                "todaySellOpenTradeValue": [0.0],
                "todaySellCloseTradeVolume": [100],
                "todaySellCloseTradeValue": [1250.0],
            }
        )
        session = Mock()
        session.run.side_effect = [statistics, positions]
        backtest_result = BacktestResult(session=session)

        self.assertIs(backtest_result.daily_trading_statistics, statistics)
        result = backtest_result.daily_positions

        self.assertEqual(result["todaySellVolume"].tolist(), [100])
        self.assertEqual(
            session.run.call_args_list,
            [
                call("Backtest::getDailyTradingStatistics(coreBacktestEngine)"),
                call("Backtest::getDailyPosition(coreBacktestEngine)"),
            ],
        )

    def test_empty_daily_positions_does_not_download_statistics(self) -> None:
        positions = pd.DataFrame()
        session = Mock()
        session.run.return_value = positions

        result = BacktestResult(session=session).daily_positions

        self.assertIs(result, positions)
        session.run.assert_called_once_with(
            "Backtest::getDailyPosition(coreBacktestEngine)"
        )

    def test_daily_positions_aggregates_duplicate_sell_statistics(self) -> None:
        positions = pd.DataFrame(
            {
                "symbol": ["000001.XSHE"],
                "tradeDate": pd.to_datetime(["2026-01-06"]),
                "todaySellVolume": [0],
                "todaySellValue": [0.0],
            }
        )
        statistics = pd.DataFrame(
            {
                "symbol": ["000001.XSHE", "000001.XSHE"],
                "tradeDate": pd.to_datetime(["2026-01-06", "2026-01-06"]),
                "todaySellOpenTradeVolume": [10, 30],
                "todaySellOpenTradeValue": [100.0, 330.0],
                "todaySellCloseTradeVolume": [20, 40],
                "todaySellCloseTradeValue": [220.0, 480.0],
            }
        )
        session = Mock()
        session.run.side_effect = [positions, statistics]

        result = BacktestResult(session=session).daily_positions

        self.assertEqual(result["todaySellVolume"].tolist(), [100])
        self.assertEqual(result["todaySellValue"].tolist(), [1130.0])

    def test_daily_positions_reports_all_missing_standardization_columns(
        self,
    ) -> None:
        positions = pd.DataFrame(
            {
                "symbol": ["000001.XSHE"],
                "tradeDate": pd.to_datetime(["2026-01-06"]),
                "todaySellVolume": [0],
            }
        )
        statistics = pd.DataFrame(
            {
                "symbol": ["000001.XSHE"],
                "tradeDate": pd.to_datetime(["2026-01-06"]),
                "todaySellOpenTradeVolume": [0],
                "todaySellOpenTradeValue": [0.0],
                "todaySellCloseTradeVolume": [100],
            }
        )
        session = Mock()
        session.run.side_effect = [positions, statistics]

        with self.assertRaises(ValueError) as raised:
            BacktestResult(session=session).daily_positions

        message = str(raised.exception)
        self.assertIn("todaySellValue", message)
        self.assertIn("todaySellCloseTradeValue", message)


if __name__ == "__main__":
    unittest.main()
