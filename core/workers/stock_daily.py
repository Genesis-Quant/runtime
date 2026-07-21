"""定义股票行情相关接口各自独立的数据更新 Worker。"""

import pandas as pd

from core.utils import pro, ts

from .base import StockWorker


class StockDailyWorker(StockWorker):
    """通过 daily 接口更新未复权日行情。"""

    factors = (
        "open",
        "high",
        "low",
        "close",
        "change",
        "pct_chg",
        "vol",
        "amount",
    )

    def fetch_one(
        self,
        code: str,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """获取一只股票的未复权日行情。"""
        response = pro.daily(
            ts_code=code,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        if response is not None and not isinstance(response, pd.DataFrame):
            raise TypeError("daily 返回值不是 DataFrame")
        data = (
            None
            if response is None
            else response.rename(columns={"trade_date": "time"})
        )
        return self.to_long(
            code,
            data,
            start_date=start_date,
            end_date=end_date,
        )


class StockDailyBasicWorker(StockWorker):
    """通过 daily_basic 接口更新每日估值和市值指标。"""

    factors = (
        "turnover_rate",
        "turnover_rate_f",
        "volume_ratio",
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

    def fetch_one(
        self,
        code: str,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """获取一只股票的每日估值和市值指标。"""
        response = pro.daily_basic(
            ts_code=code,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        if response is not None and not isinstance(response, pd.DataFrame):
            raise TypeError("daily_basic 返回值不是 DataFrame")
        data = (
            None
            if response is None
            else response.rename(columns={"trade_date": "time"})
        )
        return self.to_long(
            code,
            data,
            start_date=start_date,
            end_date=end_date,
        )


class StockAdjFactorWorker(StockWorker):
    """通过 adj_factor 接口更新复权因子。"""

    factors = ("adj_factor",)

    def fetch_one(
        self,
        code: str,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """获取一只股票的复权因子。"""
        response = pro.adj_factor(
            ts_code=code,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        if response is not None and not isinstance(response, pd.DataFrame):
            raise TypeError("adj_factor 返回值不是 DataFrame")
        data = (
            None
            if response is None
            else response.rename(columns={"trade_date": "time"})
        )
        return self.to_long(
            code,
            data,
            start_date=start_date,
            end_date=end_date,
        )


class StockQfqWorker(StockWorker):
    """通过 pro_bar 接口更新前复权日行情。"""

    factors = (
        "open_qfq",
        "high_qfq",
        "low_qfq",
        "close_qfq",
        "change_qfq",
        "pct_chg_qfq",
    )

    def fetch_one(
        self,
        code: str,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """获取一只股票的前复权日行情。"""
        response = ts.pro_bar(
            ts_code=code,
            adj="qfq",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        if response is not None and not isinstance(response, pd.DataFrame):
            raise TypeError("pro_bar[qfq] 返回值不是 DataFrame")
        data = None if response is None else response.rename(
            columns={
                "trade_date": "time",
                "open": "open_qfq",
                "high": "high_qfq",
                "low": "low_qfq",
                "close": "close_qfq",
                "change": "change_qfq",
                "pct_chg": "pct_chg_qfq",
            }
        )
        return self.to_long(
            code,
            data,
            start_date=start_date,
            end_date=end_date,
        )


class StockHfqWorker(StockWorker):
    """通过 pro_bar 接口更新后复权日行情。"""

    factors = (
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
        response = ts.pro_bar(
            ts_code=code,
            adj="hfq",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        if response is not None and not isinstance(response, pd.DataFrame):
            raise TypeError("pro_bar[hfq] 返回值不是 DataFrame")
        data = None if response is None else response.rename(
            columns={
                "trade_date": "time",
                "open": "open_hfq",
                "high": "high_hfq",
                "low": "low_hfq",
                "close": "close_hfq",
                "change": "change_hfq",
                "pct_chg": "pct_chg_hfq",
            }
        )
        return self.to_long(
            code,
            data,
            start_date=start_date,
            end_date=end_date,
        )


stock_daily_worker = StockDailyWorker(threads=4, throttle=8)
stock_daily_basic_worker = StockDailyBasicWorker(threads=4, throttle=8)
stock_adj_factor_worker = StockAdjFactorWorker(threads=4, throttle=8)
stock_qfq_worker = StockQfqWorker(threads=4, throttle=8)
stock_hfq_worker = StockHfqWorker(threads=4, throttle=8)
