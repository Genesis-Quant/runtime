"""定义持有 DolphinDB DOS 结果脚本的惰性回测结果。"""

from typing import Any

import pandas as pd

from runtime.utils import SessionResult


def _standardize_daily_positions(
    daily_positions: pd.DataFrame,
    daily_trading_statistics: pd.DataFrame,
) -> pd.DataFrame:
    """使用逐证券成交统计修正插件未填充的当日卖出字段。"""
    if daily_positions.empty:
        return daily_positions

    position_columns = {
        "symbol",
        "tradeDate",
        "todaySellVolume",
        "todaySellValue",
    }
    statistic_columns = {
        "symbol",
        "tradeDate",
        "todaySellOpenTradeVolume",
        "todaySellOpenTradeValue",
        "todaySellCloseTradeVolume",
        "todaySellCloseTradeValue",
    }
    missing_positions = position_columns.difference(daily_positions.columns)
    missing_statistics = statistic_columns.difference(
        daily_trading_statistics.columns
    )
    if missing_positions or missing_statistics:
        missing = sorted(missing_positions | missing_statistics)
        raise ValueError(f"回测卖出字段标准化缺少列：{missing}")

    statistics = daily_trading_statistics.assign(
        _today_sell_volume=(
            daily_trading_statistics["todaySellOpenTradeVolume"].fillna(0)
            + daily_trading_statistics["todaySellCloseTradeVolume"].fillna(0)
        ),
        _today_sell_value=(
            daily_trading_statistics["todaySellOpenTradeValue"].fillna(0)
            + daily_trading_statistics["todaySellCloseTradeValue"].fillna(0)
        ),
    )
    statistics = statistics.groupby(
        ["symbol", "tradeDate"],
        as_index=True,
        dropna=False,
    )[["_today_sell_volume", "_today_sell_value"]].sum()
    position_keys = pd.MultiIndex.from_frame(
        daily_positions[["symbol", "tradeDate"]]
    )
    corrected = statistics.reindex(position_keys).fillna(0)

    result = daily_positions.copy()
    result["todaySellVolume"] = pd.Series(
        pd.array(
            corrected["_today_sell_volume"].to_numpy(),
            dtype=daily_positions["todaySellVolume"].dtype,
        ),
        index=result.index,
    )
    result["todaySellValue"] = pd.Series(
        pd.array(
            corrected["_today_sell_value"].to_numpy(),
            dtype=daily_positions["todaySellValue"].dtype,
        ),
        index=result.index,
    )
    return result


class BacktestResult(SessionResult):
    """按需下载标准结果，并提供仅限直接 Python 调用的派生与诊断属性。"""

    def __init__(self, *, session: Any) -> None:
        super().__init__(session=session)
        self._daily_trading_statistics_cache: pd.DataFrame | None = None

    @property
    def trade_details(self) -> pd.DataFrame:
        """访问时生成并下载成交明细。"""
        return self.download("Backtest::getTradeDetails(coreBacktestEngine)")

    @property
    def daily_positions(self) -> pd.DataFrame:
        """下载每日持仓，并用逐证券成交统计修正当日卖出字段。"""
        daily_positions = self.download(
            "Backtest::getDailyPosition(coreBacktestEngine)"
        )
        if daily_positions.empty:
            return daily_positions
        daily_trading_statistics = self.daily_trading_statistics
        return _standardize_daily_positions(
            daily_positions,
            daily_trading_statistics,
        )

    @property
    def daily_portfolios(self) -> pd.DataFrame:
        """访问时生成并下载每日组合资产。"""
        return self.download("Backtest::getDailyTotalPortfolios(coreBacktestEngine)")

    @property
    def return_summary(self) -> pd.DataFrame:
        """按需计算收益汇总；它不属于 Workspace 或 CLI 标准输出。"""
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
        """首次访问时下载每日交易统计，后续标准输出复用同一结果。"""
        if self.closed:
            raise RuntimeError("结果已关闭，无法继续从 session 下载")
        if self._daily_trading_statistics_cache is None:
            self._daily_trading_statistics_cache = self.download(
                "Backtest::getDailyTradingStatistics(coreBacktestEngine)"
            )
        return self._daily_trading_statistics_cache

    @property
    def engine_stat(self) -> pd.DataFrame:
        """按需读取引擎诊断；它不属于 Workspace 或 CLI 标准输出。"""
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
                    "engine"
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
            try:
                super().close()
            finally:
                self._daily_trading_statistics_cache = None


__all__ = ["BacktestResult"]
