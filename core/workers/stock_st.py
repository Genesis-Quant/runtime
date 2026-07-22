"""按自然日增量维护稀疏存储的 ST 股票特征。"""

import pandas as pd

from core.utils import normalize_date, pro
from core.database import IS_ST_FACTOR

from .base import DateWorker


class StockSTWorker(DateWorker):
    """逐日抓取 ST 名单，只持久化 value=1 的股票。"""

    def __str__(self) -> str:
        """返回 ST 股票 Worker 标识。"""
        return "<StockSTWorker>"

    @property
    def factors(self) -> tuple[str, ...]:
        """返回 ST Worker 写入的因子。"""
        return (IS_ST_FACTOR,)

    def fetch_one(self, current_date: pd.Timestamp) -> pd.DataFrame:
        """获取一个自然日的 ST 股票名单。"""
        current = normalize_date(current_date, "current_date")
        response = self.retry(
            lambda: pro.stock_st(
                trade_date=current.strftime("%Y%m%d"),
                fields="ts_code,trade_date",
            ),
            context=f"{self}[{current:%Y-%m-%d}]",
        )

        if response is None or response.empty:
            return self.EMPTY

        data = response.rename(columns={"trade_date": "time", "ts_code": "code"})
        data[self.factors[0]] = 1.0
        return self.melt(current, data)
