"""定义所有数据更新 Worker 的统一入口和写入流程。"""

import time
from abc import ABC, abstractmethod
from typing import ClassVar, TypeVar
from collections.abc import Callable, Iterable

import pandas as pd

from config import DATA_START_DATE
from core.utils import DateLike, RateLimiter, normalize_date_range
from core.database import write_core_table

Result = TypeVar("Result")

columns = ("time", "code", "factor", "value")
empty = pd.DataFrame(columns=columns)
empty["time"] = pd.to_datetime(empty["time"])


class BaseWorker(ABC):
    """统一管理运行配置、失败重试和四列因子表批量写入。"""

    COLUMNS: ClassVar[tuple[str, ...]] = columns
    EMPTY = empty

    def __init__(
            self,
            *,
            start_date: DateLike = DATA_START_DATE,
            end_date: DateLike | None = None,
            threads: int = 3,
            throttle: int = 8,
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

        end_date = pd.Timestamp.today() if end_date is None else end_date
        self.start_date, self.end_date = normalize_date_range(
            start_date,
            end_date,
        )
        self.threads = threads
        self.max_retries = max_retries
        self.retry_interval = retry_interval
        self.batch_size = batch_size
        self.limiter = RateLimiter(throttle)

    @property
    @abstractmethod
    def factors(self) -> tuple[str, ...]:
        """返回当前 Worker 写入的全部固定因子。"""
        raise NotImplementedError

    @abstractmethod
    def fetch_all(self) -> Iterable[pd.DataFrame]:
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

    def check(self, data: pd.DataFrame):
        """校验 DataFrame"""
        if not isinstance(data, pd.DataFrame):
            raise TypeError("fetch_one 结果必须是 DataFrame")

        if missing := set(self.COLUMNS) - set(data.columns):
            raise ValueError(f"待写入数据缺少列：{sorted(missing)}")

        if not pd.api.types.is_datetime64_any_dtype(data["time"]):
            raise ValueError(f"time 列必须为 time 类型")

    def run(self) -> int:
        """忽略空结果并按累计行数分批写入 DataFrame 数据流。"""
        batch: list[pd.DataFrame] = []
        rows, total = 0, 0

        for frame in self.fetch_all():
            if frame.empty:
                continue

            batch.append(frame)
            rows += len(frame)

            if rows < self.batch_size:
                continue

            total += write_core_table(pd.concat(batch, ignore_index=True))
            batch.clear()
            rows = 0

        if batch:
            total += write_core_table(pd.concat(batch, ignore_index=True))

        return total
