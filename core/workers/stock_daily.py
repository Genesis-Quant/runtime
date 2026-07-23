"""定义股票行情相关接口各自独立的数据更新 Worker。"""

import pandas as pd

from core.utils import CODE_COLUMN, TIME_COLUMN, normalize_date, pro, ts

from .base import DateWorker, StockWorker


class StockDailyWorker(DateWorker):
    """通过 daily 接口按自然日更新全市场未复权行情。"""

    def __str__(self) -> str:
        """返回未复权日行情 Worker 标识。"""
        return "<StockDailyWorker>"

    @property
    def factors(self) -> tuple[str, ...]:
        return (
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "change",
            "pct_chg",
            "vol",
            "amount",
        )

    def fetch_one(self, current_date: pd.Timestamp) -> pd.DataFrame:
        """获取一个自然日的全市场未复权日行情。"""
        current = normalize_date(current_date, "current_date")
        response = self.retry(
            lambda: pro.daily(
                trade_date=current.strftime("%Y%m%d"),
                fields=",".join(("ts_code", "trade_date", *self.factors)),
            ),
            context=f"{self}[{current:%Y-%m-%d}]",
        )

        if response is None or response.empty:
            return self.EMPTY

        data = response.rename(
            columns={"trade_date": TIME_COLUMN, "ts_code": CODE_COLUMN}
        )
        return self.melt(current, data)


class StockLimitWorker(DateWorker):
    """通过 stk_limit 接口按自然日更新全市场涨跌停价格。"""

    def __str__(self) -> str:
        """返回涨跌停价格 Worker 标识。"""
        return "<StockLimitWorker>"

    @property
    def factors(self) -> tuple[str, ...]:
        return (
            "up_limit",
            "down_limit"
        )

    def fetch_one(self, current_date: pd.Timestamp) -> pd.DataFrame:
        """获取一个自然日的全市场涨跌停价格。"""
        current = normalize_date(current_date, "current_date")
        response = self.retry(
            lambda: pro.stk_limit(
                trade_date=current.strftime("%Y%m%d"),
                fields=",".join(("ts_code", "trade_date", *self.factors)),
            ),
            context=f"{self}[{current:%Y-%m-%d}]",
        )

        if response is None or response.empty:
            return self.EMPTY

        data = response.rename(
            columns={"trade_date": TIME_COLUMN, "ts_code": CODE_COLUMN}
        )
        return self.melt(current, data)


class StockDailyBasicWorker(DateWorker):
    """通过 daily_basic 接口按自然日更新全市场估值和市值指标。"""

    def __str__(self) -> str:
        """返回每日指标 Worker 标识。"""
        return "<StockDailyBasicWorker>"

    @property
    def factors(self) -> tuple[str, ...]:
        return (
            "turnover_rate",
            "turnover_rate_f",
            "volume_ratio",
            "limit_status",
            "pe",
            "pe_ttm",
            "pb",
            "ps",
            "ps_ttm",
            "dv_ratio",
            "dv_ttm",
            "total_share",
            "float_share",
            "free_share",
            "total_mv",
            "circ_mv",
        )

    def fetch_one(self, current_date: pd.Timestamp) -> pd.DataFrame:
        """获取一个自然日的全市场估值和市值指标。"""
        current = normalize_date(current_date, "current_date")
        response = self.retry(
            lambda: pro.daily_basic(
                trade_date=current.strftime("%Y%m%d"),
                fields=",".join(("ts_code", "trade_date", *self.factors)),
            ),
            context=f"{self}[{current:%Y-%m-%d}]",
        )

        if response is None or response.empty:
            return self.EMPTY

        data = response.rename(
            columns={"trade_date": TIME_COLUMN, "ts_code": CODE_COLUMN}
        )
        return self.melt(current, data)


class StockAdjFactorWorker(DateWorker):
    """通过 adj_factor 接口按自然日更新全市场复权因子。"""

    def __str__(self) -> str:
        """返回复权因子 Worker 标识。"""
        return "<StockAdjFactorWorker>"

    @property
    def factors(self) -> tuple[str, ...]:
        return ("adj_factor",)

    def fetch_one(self, current_date: pd.Timestamp) -> pd.DataFrame:
        """获取一个自然日的全市场复权因子。"""
        current = normalize_date(current_date, "current_date")
        response = self.retry(
            lambda: pro.adj_factor(
                trade_date=current.strftime("%Y%m%d"),
                fields=",".join(("ts_code", "trade_date", *self.factors)),
            ),
            context=f"{self}[{current:%Y-%m-%d}]",
        )

        if response is None or response.empty:
            return self.EMPTY

        data = response.rename(
            columns={"trade_date": TIME_COLUMN, "ts_code": CODE_COLUMN}
        )
        return self.melt(current, data)


class StockHfqWorker(StockWorker):
    """通过 pro_bar 接口更新后复权日行情。"""

    def __str__(self) -> str:
        """返回后复权日行情 Worker 标识。"""
        return "<StockHfqWorker>"

    @property
    def factors(self) -> tuple[str, ...]:
        return (
            "open_hfq",
            "high_hfq",
            "low_hfq",
            "close_hfq",
            "change_hfq",
            "pct_chg_hfq",
        )

    def fetch_one(
            self,
            code: str,
            *,
            start_date: pd.Timestamp,
            end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """获取一只股票的后复权日行情。"""
        response = self.retry(
            lambda: ts.pro_bar(
                ts_code=code,
                adj="hfq",
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
            ),
            context=f"{self}[{code}]",
        )

        if response is None or response.empty:
            return self.EMPTY

        return self.melt(code, response.rename(
            columns={
                "trade_date": TIME_COLUMN,
                "open": "open_hfq",
                "high": "high_hfq",
                "low": "low_hfq",
                "close": "close_hfq",
                "change": "change_hfq",
                "pct_chg": "pct_chg_hfq",
            }
        ), start_date=start_date, end_date=end_date)
