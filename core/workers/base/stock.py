"""定义逐股票更新单个接口的抽象 Worker。"""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from functools import partial

import numpy as np
import pandas as pd

from core.database import CORE_TABLE, create_session
from core.utils import DateLike, codes, normalize_date

from .worker import BaseWorker


class StockWorker(BaseWorker, ABC):
    """按股票并发调用单个固定数据接口。"""

    @property
    def last_date_factors(self) -> tuple[str, ...]:
        """返回用于判断该接口最近更新日期的因子集合。"""
        return self.factors

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

    def get_last_dates(
        self,
        codes: Sequence[str],
    ) -> dict[str, pd.Timestamp]:
        """返回每只股票固定回执因子最近有数据的日期。"""
        last_date_factors = self.last_date_factors
        if not last_date_factors:
            raise ValueError(
                f"{type(self).__name__}.last_date_factors 不能为空"
            )
        if invalid := set(last_date_factors) - set(self.factors):
            raise ValueError(
                f"{type(self).__name__}.last_date_factors 包含未声明因子："
                f"{sorted(invalid)}"
            )
        session = create_session()
        try:
            session.upload(
                {
                    "stockWorkerCodes": np.asarray(codes, dtype=str),
                    "stockWorkerLastDateFactors": np.asarray(
                        last_date_factors, dtype=str
                    ),
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

    def fetch_all(
        self,
        current_date: DateLike | None = None,
    ) -> Iterable[pd.DataFrame]:
        """根据每只股票的最近数据日并发调用 fetch_one(code)。"""
        last_dates = self.get_last_dates(codes)
        end_date = normalize_date(
            pd.Timestamp.today() if current_date is None else current_date,
            "current_date",
        )
        failures: list[str] = []
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = {}
            for code in codes:
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
                except Exception as error:
                    failures.append(f"{code}: {error}")
                    continue
                if not frame.empty:
                    yield frame
        if failures:
            raise RuntimeError(
                f"{type(self).__name__} 更新失败：" + "；".join(failures)
            )
