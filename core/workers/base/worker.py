"""定义所有数据更新 Worker 的统一入口和写入流程。"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
import time
from typing import ClassVar, TypeVar

import numpy as np
import pandas as pd

from config import DATA_START_DATE
from core.database import write_core_table
from core.utils import DateLike, RateLimiter, normalize_date


Result = TypeVar("Result")


class BaseWorker(ABC):
    """统一管理运行配置、失败重试和四列因子表批量写入。"""

    COLUMNS: ClassVar[tuple[str, ...]] = ("time", "code", "factor", "value")

    def __init__(
        self,
        *,
        start_date: DateLike = DATA_START_DATE,
        threads: int = 1,
        throttle: int = 0,
        max_retries: int = 3,
        retry_interval: float = 1.0,
        batch_size: int = 200_000,
    ) -> None:
        """初始化所有 Worker 共享的日期、限流、重试和写入配置。"""
        factors = self.factors
        if not factors or len(factors) != len(set(factors)):
            raise TypeError(f"{type(self).__name__}.factors 定义无效")
        if threads <= 0:
            raise ValueError("threads 必须大于 0")
        if throttle < 0:
            raise ValueError("throttle 不能小于 0")
        if max_retries <= 0:
            raise ValueError("max_retries 必须大于 0")
        if retry_interval < 0:
            raise ValueError("retry_interval 不能小于 0")
        if batch_size <= 0:
            raise ValueError("batch_size 必须大于 0")

        self.start_date = normalize_date(start_date, "start_date")
        self.threads = threads
        self.max_retries = max_retries
        self.retry_interval = retry_interval
        self.batch_size = batch_size
        self.limiter = RateLimiter(throttle)

    def run(self, current_date: DateLike | None = None) -> int:
        """获取截止指定日期的全部增量数据并统一分批写入。"""
        return self.write_stream(self.fetch_all(current_date))

    @property
    @abstractmethod
    def factors(self) -> tuple[str, ...]:
        """返回当前 Worker 写入的全部固定因子。"""
        raise NotImplementedError

    @abstractmethod
    def fetch_all(
        self,
        current_date: DateLike | None = None,
    ) -> Iterable[pd.DataFrame]:
        """由二级任务基类遍历日期或股票并生成增量数据。"""
        raise NotImplementedError

    def retry(
        self,
        operation: Callable[[], Result],
        *,
        context: str,
    ) -> Result:
        """执行一次受限请求，失败时按配置重试。"""
        attempt = 0
        while True:
            attempt += 1
            try:
                self.limiter.acquire()
                return operation()
            except Exception as error:
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        f"{context} 获取失败，已重试 {self.max_retries} 次：{error}"
                    ) from error
                time.sleep(self.retry_interval)

    def to_long(
        self,
        code: str,
        data: pd.DataFrame | None,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """把单只股票的接口宽表转换为统一四列长表。"""
        if data is None:
            return pd.DataFrame(columns=self.COLUMNS)
        if not isinstance(data, pd.DataFrame):
            raise TypeError(f"{type(self).__name__}[{code}] 返回值不是 DataFrame")
        if data.empty:
            return pd.DataFrame(columns=self.COLUMNS)
        required = {"time", *self.factors}
        if missing := required - set(data.columns):
            raise ValueError(
                f"{type(self).__name__}[{code}] 返回结果缺少列：{sorted(missing)}"
            )
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

    @classmethod
    def prepare_insert(cls, data: pd.DataFrame) -> pd.DataFrame:
        """选择统一四列，供具体 Worker 继续校验自身数据约束。"""
        if missing := set(cls.COLUMNS) - set(data.columns):
            raise ValueError(f"待写入数据缺少列：{sorted(missing)}")
        return data.loc[:, list(cls.COLUMNS)].copy()

    @classmethod
    def insert(cls, data: pd.DataFrame) -> int:
        """校验 DataFrame 并把非空四列表写入统一因子表。"""
        if not isinstance(data, pd.DataFrame):
            raise TypeError("待写入数据必须是 DataFrame")
        if data.empty:
            return 0
        return write_core_table(cls.prepare_insert(data))

    def write_stream(self, frames: Iterable[pd.DataFrame]) -> int:
        """忽略空结果并按累计行数分批写入 DataFrame 数据流。"""
        batch: list[pd.DataFrame] = []
        rows = 0
        total = 0
        for frame in frames:
            if frame.empty:
                continue
            batch.append(frame)
            rows += len(frame)
            if rows < self.batch_size:
                continue
            total += self.insert(pd.concat(batch, ignore_index=True))
            batch.clear()
            rows = 0
        if batch:
            total += self.insert(pd.concat(batch, ignore_index=True))
        return total
