"""定义逐股票更新单个接口的抽象 Worker。"""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from functools import partial

import numpy as np
import pandas as pd

from config import DATA_START_DATE
from core.utils import DateLike, CODES
from core.database import CORE_TABLE, create_session

from .worker import BaseWorker


class StockWorker(BaseWorker, ABC):
    """按股票并发调用单个固定数据接口。"""

    def __init__(
            self,
            codes: Sequence[str] = CODES,
            *,
            start_date: DateLike = DATA_START_DATE,
            end_date: DateLike | None = None,
            threads: int = 3,
            throttle: int = 8,
            max_retries: int = 3,
            retry_interval: float = 1.0,
            batch_size: int = 200_000,
    ):
        super().__init__(
            start_date=start_date,
            end_date=end_date,
            threads=threads,
            throttle=throttle,
            max_retries=max_retries,
            retry_interval=retry_interval,
            batch_size=batch_size
        )
        self.codes = codes

    def get_last_dates(self) -> dict[str, pd.Timestamp]:
        session = create_session()
        try:
            session.upload(
                {
                    "stockWorkerCodes": np.asarray(self.codes, dtype=str),
                    "stockWorkerLastDateFactors": np.asarray(self.factors, dtype=str),
                }
            )
            result = session.run(
                f"""
                select code, max(time) as time
                from {CORE_TABLE}
                where code in symbol(stockWorkerCodes)
                  and factor in symbol(stockWorkerLastDateFactors)
                group by code
                """
            )
        finally:
            session.close()
        if result is None or result.empty:
            return {}
        return {
            str(row.code): pd.Timestamp(row.time).normalize()
            for row in result.itertuples(index=False)
            if not pd.isna(row.time)
        }

    def melt(
            self,
            code: str,
            data: pd.DataFrame,
            *,
            start_date: pd.Timestamp,
            end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """把单只股票的接口宽表转换为统一四列长表。"""
        if not isinstance(data, pd.DataFrame):
            raise TypeError(f"{type(self).__name__}[{code}] 返回值不是 DataFrame")
        if data.empty:
            return self.EMPTY
        required = {"time", *self.factors}
        if missing := required - set(data.columns):
            raise ValueError(f"{type(self).__name__}[{code}] 返回结果缺少列：{sorted(missing)}")
        result = data.loc[:, ["time", *self.factors]].copy()
        result["time"] = pd.to_datetime(result["time"], errors="coerce")
        if result["time"].isna().any():
            raise ValueError(f"{type(self).__name__}[{code}] 返回了无效 time")
        result = result[result["time"].between(start_date, end_date)]
        result["code"] = code
        result = result.melt(
            id_vars=["time", "code"],
            value_vars=list(self.factors),
            var_name="factor",
            value_name="value",
        )
        result["value"] = pd.to_numeric(result["value"], errors="coerce")
        return (
            result.replace([np.inf, -np.inf], np.nan)
            .dropna(subset=["value"])
            .drop_duplicates(["time", "code", "factor"], keep="last")
            .sort_values(["factor", "time"])
            .reset_index(drop=True)
        )

    @abstractmethod
    def fetch_one(
            self,
            code: str,
            *,
            start_date: pd.Timestamp,
            end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """获取并转换一只股票在增量区间内的数据。"""
        raise NotImplementedError

    def fetch_all(self) -> Iterable[pd.DataFrame]:
        """根据每只股票的最近数据日并发调用 fetch_one(code)。"""
        last_dates = self.get_last_dates()
        end_date = self.end_date

        failures: list[str] = []
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = {}
            for code in self.codes:
                last_date = last_dates.get(code)
                start_date = (
                    self.start_date
                    if last_date is None
                    else last_date + timedelta(days=1)
                )
                if start_date > end_date:
                    continue
                future = executor.submit(
                    self.retry,
                    partial(
                        self.fetch_one,
                        code,
                        start_date=start_date,
                        end_date=end_date,
                    ),
                    context=f"{type(self).__name__}[{code}]",
                )
                futures[future] = code
            for future in as_completed(futures):
                code = futures[future]
                try:
                    frame = future.result()
                    self.check(frame)
                except Exception as error:
                    failures.append(f"{code}: {error}")
                    continue

                yield frame
        if failures:
            raise RuntimeError(
                f"{type(self).__name__} 更新失败：" + "；".join(failures)
            )
