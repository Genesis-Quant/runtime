"""定义逐自然日更新的抽象 Worker。"""
import time
from abc import ABC, abstractmethod
from datetime import timedelta
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from config import DATA_START_DATE
from core.utils import DateLike, logger, normalize_date
from core.database import CORE_TABLE, CoreTableWriter, create_session

from .worker import BaseWorker


_MAX_FAILURE_SAMPLES = 10
_MAX_ERROR_TEXT_LENGTH = 300


def _short_error(error: Exception) -> str:
    """返回适合单行日志的有界异常摘要。"""
    detail = " ".join(str(error).split())
    text = type(error).__name__ if not detail else f"{type(error).__name__}: {detail}"
    if len(text) <= _MAX_ERROR_TEXT_LENGTH:
        return text
    return text[:_MAX_ERROR_TEXT_LENGTH - 1] + "…"


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
            logger.info(
                f"{self} 更新计划：无需更新，"
                f"实际起始日={start_date:%Y-%m-%d}，"
                f"结束日={end_date:%Y-%m-%d}，自然日=0，chunk=0"
            )
            return pd.DatetimeIndex([])

        dates = pd.date_range(start_date, end_date, freq="D")
        chunk_count = (len(dates) + self.chunk_size - 1) // self.chunk_size
        mode = "全量" if last_date is None else "增量"
        logger.info(
            f"{self} 更新计划：模式={mode}，"
            f"实际区间={dates[0]:%Y-%m-%d} 至 {dates[-1]:%Y-%m-%d}，"
            f"自然日={len(dates):,}，chunk={chunk_count:,}"
        )
        return dates

    def get_last_date(self) -> pd.Timestamp | None:
        """返回当前 Worker 对应因子最近有数据的自然日。"""
        started = time.perf_counter()
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
            elapsed = time.perf_counter() - started
            logger.info(
                f"{self} 增量基线：因子={len(self.factors):,}，"
                f"最近数据日=无，查询耗时={elapsed:.2f}秒"
            )
            return None
        value = result.iloc[0]["time"]
        if pd.isna(value):
            elapsed = time.perf_counter() - started
            logger.info(
                f"{self} 增量基线：因子={len(self.factors):,}，"
                f"最近数据日=无，查询耗时={elapsed:.2f}秒"
            )
            return None
        latest = pd.Timestamp(value).normalize()
        elapsed = time.perf_counter() - started
        logger.info(
            f"{self} 增量基线：因子={len(self.factors):,}，"
            f"最近数据日={latest:%Y-%m-%d}，"
            f"查询耗时={elapsed:.2f}秒"
        )
        return latest

    @abstractmethod
    def fetch_one(self, current_date: pd.Timestamp) -> pd.DataFrame:
        """返回一个自然日已规范的四列长表，空结果返回 ``self.EMPTY``。

        实现应把接口宽表交给 :meth:`melt` 并直接返回其结果，不得返回
        ``None``、接口原始宽表，或在 ``melt`` 之后再次清洗。
        所有外部请求必须通过 :meth:`retry` 或
        :meth:`fetch_paginated` 发起，以共享 Worker 的限流和重试配置。
        """
        raise NotImplementedError

    def fetch_all(self) -> Iterable[pd.DataFrame]:
        """按块并发获取，按日期顺序生成可直接写入的完整 chunk。"""
        started = time.perf_counter()
        self._reset_pagination_stats()
        dates = self.pending_dates()
        chunk_count = (len(dates) + self.chunk_size - 1) // self.chunk_size
        rows, nonempty_count, empty_count, failed_count = 0, 0, 0, 0

        if dates.empty:
            elapsed = time.perf_counter() - started
            logger.info(
                f"{self} 获取汇总：状态=完成，"
                f"日期=0/0，非空=0，空=0，"
                f"结果行=0，失败=0，耗时={elapsed:.2f}秒"
            )
            return

        # 一个线程池覆盖全部 chunk，避免每十天反复创建和销毁线程。
        status = "进行中"
        try:
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
                        chunk_failure_count = 0
                        logger.debug(
                            f"{self} 获取 chunk {chunk_number}/"
                            f"{chunk_count}：{chunk[0]:%Y-%m-%d} 至 "
                            f"{chunk[-1]:%Y-%m-%d}"
                        )

                        futures = {
                            executor.submit(
                                self.fetch_one,
                                date_value,
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
                                failed_count += 1
                                chunk_failure_count += 1
                                if len(failures) < _MAX_FAILURE_SAMPLES:
                                    error_text = _short_error(error)
                                    failures.append(
                                        f"{date_value:%Y-%m-%d}: {error_text}"
                                    )
                                    logger.error(
                                        f"{self}"
                                        f"[{date_value:%Y-%m-%d}] "
                                        f"获取失败：{error_text}"
                                    )
                            else:
                                rows += len(frame)
                                nonempty_count += int(not frame.empty)
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

                        if chunk_failure_count:
                            omitted_count = (
                                chunk_failure_count - len(failures)
                            )
                            omitted = (
                                f"；其余 {omitted_count:,} 条失败已省略"
                                if omitted_count
                                else ""
                            )
                            raise RuntimeError(
                                f"{self} chunk "
                                f"{chunk[0]:%Y-%m-%d} 至 {chunk[-1]:%Y-%m-%d} "
                                f"获取失败，共 {chunk_failure_count:,} 个自然日；"
                                "失败样例：" + "；".join(failures) + omitted
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
            status = "完成"
        except GeneratorExit:
            status = "中止"
            raise
        except BaseException:
            status = "失败"
            raise
        finally:
            elapsed = time.perf_counter() - started
            completed_count = nonempty_count + empty_count + failed_count
            logger.info(
                f"{self} 获取汇总：状态={status}，"
                f"日期={completed_count:,}/{len(dates):,}，"
                f"非空={nonempty_count:,}，空={empty_count:,}，"
                f"结果行={rows:,}，失败={failed_count:,}"
                f"{self._pagination_summary()}，耗时={elapsed:.2f}秒"
            )

    def run(self) -> int:
        """按时间顺序写入完整 chunk，并返回实际写入总行数。"""
        name = str(self)
        started = time.perf_counter()
        self._partial_write_rows = 0
        throttle_text = (
            "不限速"
            if self.throttle == 0
            else f"{self.throttle:,}次/秒"
        )
        logger.info(
            f"{name} 开始更新："
            f"{self.start_date:%Y-%m-%d} 至 {self.end_date:%Y-%m-%d}，"
            f"因子={len(self.factors):,}，线程={self.threads:,}，"
            f"限速={throttle_text}，"
            f"chunk={self.chunk_size:,}天，批量={self.batch_size:,}行"
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
            total += self._partial_write_rows
            self._partial_write_rows = 0
            elapsed = time.perf_counter() - started
            logger.exception(
                f"{name} 更新失败：已确认写入={total:,}行，"
                f"耗时={elapsed:.2f}秒，"
                f"error={type(error).__name__}: {error}"
            )
            raise

        elapsed = time.perf_counter() - started
        throughput = total / elapsed if elapsed else 0.0
        logger.success(
            f"{name} 更新完成：写入={total:,}行，"
            f"耗时={elapsed:.2f}秒，吞吐={throughput:,.0f}行/秒"
        )
        return total
