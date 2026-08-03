"""定义持有 DolphinDB DOS 结果脚本的惰性回测结果。"""

from typing import Any

import pandas as pd

from runtime.utils import SessionResult


class BacktestResult(SessionResult):
    """按需生成并下载已结束回测的标准输出。"""

    @property
    def trade_details(self) -> pd.DataFrame:
        """访问时生成并下载成交明细。"""
        return self.download("Backtest::getTradeDetails(coreBacktestEngine)")

    @property
    def daily_positions(self) -> pd.DataFrame:
        """访问时生成并下载每日持仓。"""
        return self.download("Backtest::getDailyPosition(coreBacktestEngine)")

    @property
    def daily_portfolios(self) -> pd.DataFrame:
        """访问时生成并下载每日组合资产。"""
        return self.download("Backtest::getDailyTotalPortfolios(coreBacktestEngine)")

    @property
    def return_summary(self) -> pd.DataFrame:
        """访问时生成并下载收益汇总。"""
        return self.download(
            """
            backtest::standardize_return_summary(
                Backtest::getReturnSummary(coreBacktestEngine),
                Backtest::getDailyTotalPortfolios(coreBacktestEngine),
                coreBacktestAnnualTradingDays,
                coreBacktestRiskFreeRate
            )
            """
        )

    @property
    def daily_trading_statistics(self) -> pd.DataFrame:
        """访问时生成并下载每日交易统计。"""
        return self.download("Backtest::getDailyTradingStatistics(coreBacktestEngine)")

    @property
    def engine_stat(self) -> pd.DataFrame:
        """访问时生成并下载回测引擎统计。"""
        return self.download("Backtest::getBacktestEngineStat(coreBacktestEngine)")

    @property
    def context(self) -> Any:
        """访问时生成并下载已移除内部对象的策略上下文。"""
        return self.download(
            """
            coreBacktestContext =
                Backtest::getContextDict(coreBacktestEngine)
            erase!(
                coreBacktestContext,
                [
                    "engine",
                    "coreBacktestUnfilteredFactorData",
                    "coreBacktestFilteredFactorData"
                ]
            )
            coreBacktestContext
            """
        )

    def close(self) -> None:
        """销毁回测引擎并关闭 DolphinDB session。"""
        if self.closed:
            return
        try:
            self.session.run("Backtest::dropBacktestEngine(coreBacktestEngine)")
        finally:
            super().close()


__all__ = ["BacktestResult"]
