"""定义逐自然日更新的抽象 Worker。"""
from abc import ABC, abstractmethod
from datetime import timedelta
from functools import partial
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

from core.utils import normalize_date
from core.database import CORE_TABLE, create_session

from .worker import BaseWorker


class DateWorker(BaseWorker, ABC):
    """从数据库最近数据日的下一自然日开始逐日调用具体接口。"""

    def melt(
            self,
            current_date: pd.Timestamp,
            data: pd.DataFrame,
    ) -> pd.DataFrame:
        """把单日接口宽表转换为统一四列长表。"""
        if not isinstance(data, pd.DataFrame):
            raise TypeError(
                f"{type(self).__name__}[{current_date:%Y-%m-%d}] "
                "返回值不是 DataFrame"
            )
        if data.empty:
            return self.EMPTY
        required = {"time", "code", *self.factors}
        if missing := required - set(data.columns):
            raise ValueError(
                f"{type(self).__name__}[{current_date:%Y-%m-%d}] "
                f"返回结果缺少列：{sorted(missing)}"
            )
        result = data.loc[:, ["time", "code", *self.factors]].copy()
        result["time"] = pd.to_datetime(result["time"], errors="coerce")
        if result["time"].isna().any():
            raise ValueError(
                f"{type(self).__name__}[{current_date:%Y-%m-%d}] "
                "返回了无效 time"
            )
        result = result[result["time"].dt.normalize().eq(current_date)]
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
            .sort_values(["factor", "code", "time"])
            .reset_index(drop=True)
        )

    def pending_dates(self) -> pd.DatetimeIndex:
        """返回最新回执之后到当前日期之间的全部自然日。"""
        last_date = self.get_last_date()
        start_date = (
            self.start_date
            if last_date is None
            else normalize_date(last_date, "last_date") + timedelta(days=1)
        )
        end_date = self.end_date

        if start_date > end_date:
            return pd.DatetimeIndex([])
        return pd.date_range(start_date, end_date, freq="D")

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

    @abstractmethod
    def fetch_one(self, current_date: pd.Timestamp) -> pd.DataFrame:
        """获取并规范化一个自然日的数据。"""
        raise NotImplementedError

    def fetch_all(self) -> Iterable[pd.DataFrame]:
        """根据整体最近数据日并发调用 fetch_one(date)。"""
        failures: list[str] = []
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = {
                executor.submit(
                    self.retry,
                    partial(self.fetch_one, date_value),
                    context=f"{type(self).__name__}[{date_value:%Y-%m-%d}]",
                ): date_value
                for date_value in self.pending_dates()
            }

            for future in as_completed(futures):
                date_value = futures[future]
                print(date_value)
                try:
                    frame = future.result()
                    self.check(frame)
                except Exception as error:
                    failures.append(f"{date_value:%Y-%m-%d}: {error}")
                    continue

                yield frame
        if failures:
            raise RuntimeError(
                f"{type(self).__name__} 更新失败：" + "；".join(failures)
            )
