"""定义逐自然日更新的抽象 Worker。"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from functools import partial

import numpy as np
import pandas as pd

from core.database import CORE_TABLE, create_session
from core.utils import DateLike, normalize_date

from .worker import BaseWorker


class DateWorker(BaseWorker, ABC):
    """从数据库最近数据日的下一自然日开始逐日调用具体接口。"""

    @abstractmethod
    def fetch_one(self, current_date: pd.Timestamp) -> pd.DataFrame:
        """获取并规范化一个自然日的数据。"""
        raise NotImplementedError

    def pending_dates(
            self,
            last_date: DateLike | None,
            current_date: DateLike | None = None,
    ) -> pd.DatetimeIndex:
        """返回最新回执之后到当前日期之间的全部自然日。"""
        current = normalize_date(
            pd.Timestamp.today() if current_date is None else current_date,
            "current_date",
        )
        start = (
            self.start_date
            if last_date is None
            else normalize_date(last_date, "last_date")
                 + timedelta(days=1)
        )
        if start > current:
            return pd.DatetimeIndex([])
        return pd.date_range(start, current, freq="D")

    def get_last_date(self) -> pd.Timestamp | None:
        """返回当前 Worker 对应因子最近有数据的自然日。"""
        session = create_session()
        try:
            session.upload(
                {"dateWorkerFactors": np.asarray(self.factors, dtype=str)}
            )
            result = session.run(
                f"""
                select max(time) as time
                from {CORE_TABLE}
                where factor in symbol(dateWorkerFactors)
                """
            )
        finally:
            session.close()
        if result is None or result.empty or "time" not in result.columns:
            return None
        value = result.iloc[0]["time"]
        return None if pd.isna(value) else pd.Timestamp(value).normalize()

    def fetch_all(
            self,
            current_date: DateLike | None = None,
    ) -> Iterable[pd.DataFrame]:
        """根据整体最近数据日并发调用 fetch_one(date)。"""
        dates = self.pending_dates(self.get_last_date(), current_date)
        failures: list[str] = []
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = {
                executor.submit(
                    self.retry,
                    partial(self.fetch_one, date_value),
                    context=f"{type(self).__name__}[{date_value:%Y-%m-%d}]",
                ): date_value
                for date_value in dates
            }
            for future in as_completed(futures):
                date_value = futures[future]
                try:
                    frame = future.result()
                except Exception as error:
                    failures.append(f"{date_value:%Y-%m-%d}: {error}")
                    continue
                if not frame.empty:
                    yield frame
        if failures:
            raise RuntimeError(
                f"{type(self).__name__} 更新失败：" + "；".join(failures)
            )
