"""定义持有 DolphinDB DOS 结果脚本的惰性回测结果。"""

from typing import Any

import pandas as pd

from core.utils import SessionResult


class BacktestResult(SessionResult):
    """按需下载一次已结束回测的标准输出。"""

    def __init__(
        self,
        *,
        name: str,
        session: Any,
        compact: bool,
    ) -> None:
        super().__init__(session=session)
        self.name = name
        self.compact = compact

    @property
    def message_rows(self) -> int:
        """访问时下载回测消息行数。"""
        return self.download("coreBacktestResultMessageRows")

    @property
    def trade_details(self) -> pd.DataFrame | None:
        """访问时下载成交明细。"""
        if self.compact:
            return None
        return self.download("coreBacktestResultTradeDetails")

    @property
    def daily_positions(self) -> pd.DataFrame | None:
        """访问时下载每日持仓。"""
        if self.compact:
            return None
        return self.download("coreBacktestResultDailyPositions")

    @property
    def daily_portfolios(self) -> pd.DataFrame:
        """访问时下载每日组合资产。"""
        return self.download("coreBacktestResultDailyPortfolios")

    @property
    def return_summary(self) -> pd.DataFrame:
        """访问时下载收益汇总。"""
        return self.download("coreBacktestResultReturnSummary")

    @property
    def daily_trading_statistics(self) -> pd.DataFrame | None:
        """访问时下载每日交易统计。"""
        if self.compact:
            return None
        return self.download("coreBacktestResultDailyTradingStatistics")

    @property
    def engine_stat(self) -> pd.DataFrame | None:
        """访问时下载回测引擎统计。"""
        if self.compact:
            return None
        return self.download("coreBacktestResultEngineStat")

    @property
    def context(self) -> Any:
        """访问时下载已移除内部对象的策略上下文。"""
        if self.compact:
            return None
        return self.download("coreBacktestResultContext")


__all__ = ["BacktestResult"]
