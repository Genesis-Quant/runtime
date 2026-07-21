"""定义所有数据更新 Worker 的统一入口和写入流程。"""

import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from typing import ClassVar, TypeVar

import numpy as np
import pandas as pd

from config import DATA_START_DATE
from core.utils import DateLike, RateLimiter, logger, normalize_date_range
from core.database import CORE_COLUMNS, CoreTableWriter

Result = TypeVar("Result")


class BaseWorker(ABC):
    """统一管理运行配置、返回格式、失败重试和批量写入。"""

    COLUMNS: ClassVar[tuple[str, ...]] = CORE_COLUMNS
    EMPTY: ClassVar[pd.DataFrame] = pd.DataFrame(
        {
            "time": pd.Series(dtype="datetime64[ns]"),
            "code": pd.Series(dtype="object"),
            "factor": pd.Series(dtype="object"),
            "value": pd.Series(dtype="float64"),
        }
    )

    @abstractmethod
    def __str__(self) -> str:
        """返回用于日志输出的 Worker 标识。"""
        return "<BaseWorker>"

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
            raise TypeError(f"{self}.factors 定义无效")
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
        """生成已符合四列返回约定、可直接写入的增量数据。"""
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
                logger.warning(
                    f"{context} 第 {attempt} 次获取失败，"
                    f"{self.retry_interval:g} 秒后进行第 {attempt + 1} 次尝试："
                    f"{error}"
                )
                time.sleep(self.retry_interval)

    def normalize_result(self, data: pd.DataFrame) -> pd.DataFrame:
        """完成 ``fetch_one`` 返回前唯一一次行级规范化。

        返回值严格包含 ``time/code/factor/value`` 四列；``time`` 为
        datetime64，``code`` 和 ``factor`` 为非空字符串，``value`` 为有限
        float。空值和无穷值仅从 ``value`` 中删除，重复键保留最后一条。

        该方法只能由 ``melt`` 调用。``fetch_all``、``write`` 和数据库写入器
        均把返回值视为成品，不再转换类型、清理空值、去重或排序。
        """
        if not isinstance(data, pd.DataFrame):
            raise TypeError("待规范数据必须是 DataFrame")
        if missing := set(self.COLUMNS) - set(data.columns):
            raise ValueError(f"待规范数据缺少列：{sorted(missing)}")
        if data.empty:
            return self.EMPTY

        result = data.loc[:, list(self.COLUMNS)].copy()
        if not pd.api.types.is_datetime64_any_dtype(result["time"]):
            raise ValueError("time 列必须为 datetime64 类型")

        codes = result["code"].astype("string").str.strip()
        factors = result["factor"].astype("string").str.strip()
        invalid_keys = result["time"].isna()
        invalid_keys |= codes.isna() | codes.eq("")
        invalid_keys |= factors.isna() | factors.eq("")
        if invalid_keys.any():
            raise ValueError(
                f"待规范数据包含 {int(invalid_keys.sum())} 行无效 "
                "time/code/factor"
            )

        values = pd.to_numeric(result["value"], errors="coerce")
        result["code"] = codes.astype(object)
        result["factor"] = factors.astype(object)
        result["value"] = values.to_numpy(dtype=float, na_value=np.nan)
        result.loc[~np.isfinite(result["value"]), "value"] = np.nan

        result = (
            result.dropna(subset=["value"])
            .drop_duplicates(["time", "code", "factor"], keep="last")
            .sort_values(["factor", "code", "time"])
            .reset_index(drop=True)
        )
        return self.EMPTY if result.empty else result

    def check(self, data: pd.DataFrame) -> pd.DataFrame:
        """校验 ``fetch_one`` 的结构契约，并原样返回 DataFrame。

        本方法只检查列和 dtype，不修改数据。内容清洗必须已经由
        :meth:`normalize_result` 完成，调用方可直接使用本方法的返回值。
        """
        if not isinstance(data, pd.DataFrame):
            raise TypeError("fetch_one 结果必须是 DataFrame")
        if tuple(data.columns) != self.COLUMNS:
            raise ValueError(
                "fetch_one 结果列必须严格为 "
                f"{list(self.COLUMNS)}，实际为 {list(data.columns)}"
            )
        if not pd.api.types.is_datetime64_any_dtype(data["time"]):
            raise ValueError("fetch_one 结果的 time 列必须为 datetime64 类型")
        if not pd.api.types.is_float_dtype(data["value"]):
            raise ValueError("fetch_one 结果的 value 列必须为 float 类型")
        return data

    def write(self, writer: CoreTableWriter, data: pd.DataFrame) -> int:
        """切分已规范长表并写入，返回 DolphinDB 实际写入行数。"""
        total = 0
        # fetch_all 已保证返回契约；此处只控制网络批次，不再处理内容。
        for offset in range(0, len(data), self.batch_size):
            batch = data.iloc[offset:offset + self.batch_size]
            logger.debug(f"{self} 写入批次，共 {len(batch):,} 行")
            total += writer.append(batch)
        return total

    def run(self) -> int:
        """执行完整增量更新并返回成功写入 DolphinDB 的总行数。"""
        name = str(self)
        started = time.perf_counter()
        logger.info(
            f"{name} 开始更新："
            f"{self.start_date:%Y-%m-%d} 至 {self.end_date:%Y-%m-%d}"
        )
        batch: list[pd.DataFrame] = []
        rows, total = 0, 0
        try:
            with CoreTableWriter(
                    self.factors,
                    thread_count=self.threads,
            ) as writer:
                for frame in self.fetch_all():
                    if frame.empty:
                        continue

                    # 这里只合并小结果以减少写入次数，不重复规范化。
                    batch.append(frame)
                    rows += len(frame)

                    if rows < self.batch_size:
                        continue

                    total += self.write(
                        writer,
                        pd.concat(batch, ignore_index=True),
                    )
                    batch.clear()
                    rows = 0

                if batch:
                    total += self.write(
                        writer,
                        pd.concat(batch, ignore_index=True),
                    )
        except Exception as error:
            logger.exception(
                f"{name} 更新失败，已写入 {total:,} 行：{error}"
            )
            raise

        elapsed = time.perf_counter() - started
        logger.success(
            f"{name} 更新完成，共写入 {total:,} 行，耗时 {elapsed:.2f} 秒"
        )
        return total

    def __repr__(self) -> str:
        """返回与日志标识一致的调试字符串。"""
        return str(self)
