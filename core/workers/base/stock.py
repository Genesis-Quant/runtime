"""定义逐股票更新单个接口的抽象 Worker。"""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import timedelta
from functools import partial

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from config import DATA_START_DATE
from core.utils import CODES, DateLike, logger
from core.database import CORE_TABLE, create_session

from .worker import BaseWorker


class StockWorker(BaseWorker, ABC):
    """按股票并发调用单个固定数据接口。"""

    @abstractmethod
    def __str__(self) -> str:
        """返回用于日志输出的按股票 Worker 标识。"""
        return "<StockWorker>"

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
            batch_size: int = 1_000_000,
    ) -> None:
        """初始化按股票更新范围、股票池、并发和写入配置。"""
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
        logger.debug(
            f"{self} 初始化：股票={len(self.codes):,}，"
            f"{self.start_date:%Y-%m-%d} 至 {self.end_date:%Y-%m-%d}，"
            f"threads={self.threads}，throttle={throttle}，"
            f"max_retries={self.max_retries}，batch_size={self.batch_size}"
        )

    def get_last_dates(self) -> dict[str, pd.Timestamp]:
        """返回已有数据中每只股票的最近日期，无记录的股票不在字典中。"""
        logger.debug(
            f"{self} 查询 {len(self.codes):,} 只股票的最近数据日"
        )
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
            logger.debug(f"{self} 未查询到已有数据")
            return {}
        dates = {
            str(row.code): pd.Timestamp(row.time).normalize()
            for row in result.itertuples(index=False)
            if not pd.isna(row.time)
        }
        logger.debug(
            f"{self} 查询到 {len(dates):,} 只股票的最近数据日"
        )
        return dates

    def melt(
            self,
            code: str,
            data: pd.DataFrame,
            *,
            start_date: pd.Timestamp,
            end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """把单只股票的接口宽表转换并规范为可直接写入的四列长表。"""
        if not isinstance(data, pd.DataFrame):
            raise TypeError(f"{self}[{code}] 返回值不是 DataFrame")
        if data.empty:
            return self.EMPTY
        required = {"time", *self.factors}
        if missing := required - set(data.columns):
            raise ValueError(f"{self}[{code}] 返回结果缺少列：{sorted(missing)}")
        result = data.loc[:, ["time", *self.factors]].copy()
        result["time"] = pd.to_datetime(result["time"], errors="coerce")
        if result["time"].isna().any():
            raise ValueError(f"{self}[{code}] 返回了无效 time")
        result = result[result["time"].between(start_date, end_date)]
        result["code"] = code
        result = result.melt(
            id_vars=["time", "code"],
            value_vars=list(self.factors),
            var_name="factor",
            value_name="value",
        )
        return self.normalize_result(result)

    @abstractmethod
    def fetch_one(
            self,
            code: str,
            *,
            start_date: pd.Timestamp,
            end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        """返回一只股票已规范的四列长表，空结果返回 ``self.EMPTY``。

        实现应把接口宽表交给 :meth:`melt` 并直接返回其结果，不得返回
        ``None``、接口原始宽表，或在 ``melt`` 之后再次清洗。
        """
        raise NotImplementedError

    def fetch_all(self) -> Iterable[pd.DataFrame]:
        """按股票增量区间并发获取并生成可直接写入的四列长表。"""
        last_dates = self.get_last_dates()
        end_date = self.end_date
        tasks: list[tuple[str, pd.Timestamp]] = []
        for code in self.codes:
            last_date = last_dates.get(code)
            start_date = (
                self.start_date
                if last_date is None
                else last_date + timedelta(days=1)
            )
            if start_date <= end_date:
                tasks.append((code, start_date))

        logger.info(
            f"{self} 待更新 {len(tasks):,}/{len(self.codes):,} 只股票"
        )
        failures: list[str] = []
        rows = 0
        empty_count = 0
        task_index = 0
        ready: list[pd.DataFrame] = []
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = {}
            with tqdm(
                    total=len(tasks),
                    desc=f"{self}[{self.threads}线程]",
                    unit="code",
                    dynamic_ncols=True,
                    smoothing=0.1,
            ) as progress:
                while task_index < len(tasks) or futures or ready:
                    # 待执行 Future 最多为 threads 个，避免保留全市场结果。
                    while (
                            task_index < len(tasks)
                            and len(futures) < self.threads
                    ):
                        code, start_date = tasks[task_index]
                        future = executor.submit(
                            self.retry,
                            partial(
                                self.fetch_one,
                                code,
                                start_date=start_date,
                                end_date=end_date,
                            ),
                            context=f"{self}[{code}]",
                        )
                        futures[future] = code
                        task_index += 1

                    if ready:
                        yield ready.pop()
                        continue

                    completed, _ = wait(
                        futures,
                        return_when=FIRST_COMPLETED,
                    )
                    for future in completed:
                        code = futures.pop(future)
                        try:
                            frame = self.check(future.result())
                        except Exception as error:
                            failures.append(f"{code}: {error}")
                            logger.error(
                                f"{self}[{code}] 更新失败：{error}"
                            )
                        else:
                            rows += len(frame)
                            empty_count += int(frame.empty)
                            # 完成结果只短暂排队，下一轮立即交给 run 消费。
                            ready.append(frame)
                        finally:
                            progress.set_postfix(
                                current=code,
                                rows=f"{rows:,}",
                                empty=empty_count,
                                failed=len(failures),
                                refresh=False,
                            )
                            progress.update()
        if failures:
            logger.error(
                f"{self} 共 {len(failures):,} 只股票更新失败"
            )
            raise RuntimeError(
                f"{self} 更新失败：" + "；".join(failures)
            )
