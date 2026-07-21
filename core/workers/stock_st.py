"""按自然日增量维护稀疏存储的 ST 股票特征。"""

import numpy as np
import pandas as pd

from config import DATA_START_DATE
from core.database import IS_ST_FACTOR
from core.utils import DateLike, normalize_date, pro

from .base import DateWorker


class StockSTWorker(DateWorker):
    """逐日抓取 ST 名单，只持久化 value=1 的股票。"""

    @property
    def factors(self) -> tuple[str, ...]:
        """返回 ST Worker 写入的因子。"""
        return (IS_ST_FACTOR,)

    def __init__(
        self,
        *,
        start_date: DateLike = DATA_START_DATE,
        throttle: int = 5,
        max_retries: int = 3,
        retry_interval: float = 1.0,
        batch_size: int = 100_000,
    ) -> None:
        """使用 ST 接口默认配置初始化逐自然日流程。"""
        super().__init__(
            start_date=start_date,
            throttle=throttle,
            max_retries=max_retries,
            retry_interval=retry_interval,
            batch_size=batch_size,
        )

    @classmethod
    def normalize(cls, current_date: DateLike, data: pd.DataFrame) -> pd.DataFrame:
        """校验单日 ST 名单并转换为 value=1 的统一长表。"""
        expected = normalize_date(current_date, "current_date")
        if not isinstance(data, pd.DataFrame):
            raise TypeError(f"stock_st[{expected:%Y-%m-%d}] 返回值不是 DataFrame")
        if data.empty:
            return pd.DataFrame(columns=cls.COLUMNS)
        if missing := {"trade_date", "ts_code"} - set(data.columns):
            raise ValueError(
                f"stock_st[{expected:%Y-%m-%d}] 返回结果缺少列：{sorted(missing)}"
            )
        result = data.loc[:, ["trade_date", "ts_code"]].rename(
            columns={"trade_date": "time", "ts_code": "code"}
        )
        result["time"] = pd.to_datetime(
            result["time"],
            errors="coerce",
        ).dt.normalize()
        result["code"] = result["code"].astype("string").str.strip()
        invalid = result[["time", "code"]].isna().any(axis=1)
        invalid |= result["code"].eq("")
        if invalid.any():
            raise ValueError(
                f"stock_st[{expected:%Y-%m-%d}] 返回了 "
                f"{int(invalid.sum())} 行无效数据"
            )
        unexpected = result.loc[result["time"].ne(expected), "time"].unique()
        if len(unexpected):
            values = [
                pd.Timestamp(value).strftime("%Y-%m-%d")
                for value in unexpected
            ]
            raise ValueError(
                f"stock_st[{expected:%Y-%m-%d}] 返回了其他日期：{values}"
            )
        result = result.drop_duplicates("code", keep="last")
        result["factor"] = IS_ST_FACTOR
        result["value"] = 1.0
        return (
            result.loc[:, list(cls.COLUMNS)]
            .sort_values("code")
            .reset_index(drop=True)
        )

    def fetch_one(self, current_date: pd.Timestamp) -> pd.DataFrame:
        """请求并规范化一个自然日的 ST 股票名单。"""
        current = normalize_date(current_date, "current_date")
        response = pro.stock_st(
            trade_date=current.strftime("%Y%m%d")
        )
        if response is None:
            raise ValueError("stock_st 返回 None")
        return self.normalize(current, response)

    @classmethod
    def prepare_insert(cls, data: pd.DataFrame) -> pd.DataFrame:
        """校验统一四列表只包含稀疏存储的 ST 真值。"""
        result = super().prepare_insert(data)
        result["value"] = pd.to_numeric(result["value"], errors="coerce")
        invalid = result["factor"].astype(str).ne(IS_ST_FACTOR)
        invalid |= ~np.isclose(result["value"].to_numpy(dtype=float), 1.0)
        if invalid.any():
            raise ValueError("StockSTWorker 只允许写入 factor='is_st' 且 value=1")
        return result

stock_st_worker = StockSTWorker()
