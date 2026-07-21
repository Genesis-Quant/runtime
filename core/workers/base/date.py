"""定义逐自然日更新的抽象 Worker。"""
import time
from abc import ABC, abstractmethod
from datetime import timedelta
from functools import partial
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from config import DATA_START_DATE
from core.utils import DateLike, logger, normalize_date
from core.database import CORE_TABLE, CoreTableWriter, create_session

from .worker import BaseWorker


class DateWorker(BaseWorker, ABC):
    """从数据库最近数据日的下一自然日开始逐日调用具体接口。"""

    @abstractmethod
    def __str__(self) -> str:
        """返回用于日志输出的逐日 Worker 标识。"""
        return "<DateWorker>"

    def __init__(
            self,
            chunk_size: int = 50,
            *,
            start_date: DateLike = DATA_START_DATE,
            end_date: DateLike | None = None,
            threads: int = 3,
            throttle: int = 8,
            max_retries: int = 3,
            retry_interval: float = 1.0,
            batch_size: int = 1_000_000,
    ) -> None:
        """初始化逐日更新范围、并发配置和分块大小。"""
        self.chunk_size = chunk_size
        super().__init__(
            start_date=start_date,
            end_date=end_date,
            threads=threads,
            throttle=throttle,
            max_retries=max_retries,
            retry_interval=retry_interval,
            batch_size=batch_size,
        )
        logger.debug(
            f"{self} 初始化："
            f"{self.start_date:%Y-%m-%d} 至 {self.end_date:%Y-%m-%d}，"
            f"threads={self.threads}，throttle={throttle}，"
            f"max_retries={self.max_retries}，chunk_size={self.chunk_size}，"
            f"batch_size={self.batch_size}"
        )

    def melt(
            self,
            current_date: pd.Timestamp,
            data: pd.DataFrame,
    ) -> pd.DataFrame:
        """把单日接口宽表转换并规范为可直接写入的四列长表。"""
        if not isinstance(data, pd.DataFrame):
            raise TypeError(
                f"{self}[{current_date:%Y-%m-%d}] "
                "返回值不是 DataFrame"
            )
        if data.empty:
            return self.EMPTY
        required = {"time", "code", *self.factors}
        if missing := required - set(data.columns):
            raise ValueError(
                f"{self}[{current_date:%Y-%m-%d}] "
                f"返回结果缺少列：{sorted(missing)}"
            )
        result = data.loc[:, ["time", "code", *self.factors]].copy()
        result["time"] = pd.to_datetime(result["time"], errors="coerce")
        if result["time"].isna().any():
            raise ValueError(
                f"{self}[{current_date:%Y-%m-%d}] "
                "返回了无效 time"
            )
        result = result[result["time"].dt.normalize().eq(current_date)]
        result = result.melt(
            id_vars=["time", "code"],
            value_vars=list(self.factors),
            var_name="factor",
            value_name="value",
        )
        return self.normalize_result(result)

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
        logger.debug(f"{self} 查询最近数据日")
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
            logger.debug(f"{self} 未查询到已有数据")
            return None
        value = result.iloc[0]["time"]
        if pd.isna(value):
            logger.debug(f"{self} 未查询到已有数据")
            return None
        latest = pd.Timestamp(value).normalize()
        logger.debug(f"{self} 最近数据日为 {latest:%Y-%m-%d}")
        return latest

    @abstractmethod
    def fetch_one(self, current_date: pd.Timestamp) -> pd.DataFrame:
        """返回一个自然日已规范的四列长表，空结果返回 ``self.EMPTY``。

        实现应把接口宽表交给 :meth:`melt` 并直接返回其结果，不得返回
        ``None``、接口原始宽表，或在 ``melt`` 之后再次清洗。
        """
        raise NotImplementedError

    def fetch_all(self) -> Iterable[pd.DataFrame]:
        """按块并发获取，按日期顺序生成可直接写入的完整 chunk。"""
        dates = self.pending_dates()
        chunk_count = (len(dates) + self.chunk_size - 1) // self.chunk_size
        rows, empty_count, failed_count = 0, 0, 0
        logger.info(
            f"{self} 待更新 {len(dates):,} 个自然日，"
            f"共 {chunk_count:,} 个 chunk"
        )

        # 一个线程池覆盖全部 chunk，避免每十天反复创建和销毁线程。
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            with tqdm(
                    total=len(dates),
                    desc=f"{self}[{self.threads}线程]",
                    unit="date",
                    dynamic_ncols=True,
                    smoothing=0.1,
            ) as progress:
                for offset in range(0, len(dates), self.chunk_size):
                    chunk = dates[offset:offset + self.chunk_size]
                    chunk_number = offset // self.chunk_size + 1
                    frames: dict[pd.Timestamp, pd.DataFrame] = {}
                    failures: list[str] = []
                    logger.debug(
                        f"{self} 获取 chunk {chunk_number}/"
                        f"{chunk_count}：{chunk[0]:%Y-%m-%d} 至 "
                        f"{chunk[-1]:%Y-%m-%d}"
                    )

                    futures = {
                        executor.submit(
                            self.retry,
                            partial(self.fetch_one, date_value),
                            context=(
                                f"{self}"
                                f"[{date_value:%Y-%m-%d}]"
                            ),
                        ): date_value
                        for date_value in chunk
                    }
                    # chunk 是更新推进边界：本块全部成功后才生成结果。
                    for future in as_completed(futures):
                        date_value = futures[future]
                        try:
                            frame = self.check(future.result())
                            frames[date_value] = frame
                        except Exception as error:
                            failures.append(
                                f"{date_value:%Y-%m-%d}: {error}"
                            )
                            failed_count += 1
                            logger.error(
                                f"{self}"
                                f"[{date_value:%Y-%m-%d}] 更新失败：{error}"
                            )
                        else:
                            rows += len(frame)
                            empty_count += int(frame.empty)
                        finally:
                            progress.set_postfix(
                                current=f"{date_value:%Y-%m-%d}",
                                chunk=f"{chunk_number}/{chunk_count}",
                                rows=f"{rows:,}",
                                empty=empty_count,
                                failed=failed_count,
                                refresh=False,
                            )
                            progress.update()

                    if failures:
                        raise RuntimeError(
                            f"{self} chunk "
                            f"{chunk[0]:%Y-%m-%d} 至 {chunk[-1]:%Y-%m-%d} "
                            "更新失败：" + "；".join(failures)
                        )

                    data = [
                        frames[date]
                        for date in chunk
                        if not frames[date].empty
                    ]
                    result = (
                        pd.concat(data, ignore_index=True)
                        if data
                        else self.EMPTY
                    )
                    # fetch_one 已规范每个结果；拼接后不再二次清洗或排序。
                    logger.debug(
                        f"{self} chunk {chunk_number}/"
                        f"{chunk_count} 获取完成，共 {len(result):,} 行"
                    )
                    yield result

    def run(self) -> int:
        """按时间顺序写入完整 chunk，并返回实际写入总行数。"""
        name = str(self)
        started = time.perf_counter()
        logger.info(
            f"{name} 开始更新："
            f"{self.start_date:%Y-%m-%d} 至 {self.end_date:%Y-%m-%d}，"
            f"chunk_size={self.chunk_size}"
        )
        total = 0
        try:
            with CoreTableWriter(
                    self.factors,
                    thread_count=self.threads,
            ) as writer:
                for data in self.fetch_all():
                    if not data.empty:
                        total += self.write(writer, data)
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
