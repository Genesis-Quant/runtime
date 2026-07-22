"""定义所有数据更新 Worker 的统一入口和写入流程。"""

import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping
from threading import Lock
from typing import ClassVar, TypeVar

import numpy as np
import pandas as pd

from config import DATA_START_DATE
from core.utils import DateLike, RateLimiter, logger, normalize_date_range
from core.database import CORE_COLUMNS, CoreTableWriter

Result = TypeVar("Result")
_MAX_PAGINATION_LOG_SAMPLES = 10


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
        self.throttle = throttle
        self.max_retries = max_retries
        self.retry_interval = retry_interval
        self.batch_size = batch_size
        self.limiter = RateLimiter(throttle)
        # write() 失败时保留已成功提交的子批行数，供 run() 汇总。
        self._partial_write_rows = 0
        self._pagination_lock = Lock()
        self._pagination_stats: dict[str, int] = {}
        self._reset_pagination_stats()

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
                result = operation()
                if attempt > 1:
                    logger.info(
                        f"{context} 请求恢复："
                        f"第 {attempt}/{self.max_retries} 次尝试成功"
                    )
                return result
            except Exception as error:
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        f"{context} 获取失败，"
                        f"共尝试 {self.max_retries} 次：{error}"
                    ) from error
                logger.warning(
                    f"{context} 请求重试："
                    f"attempt={attempt}/{self.max_retries}，"
                    f"retry_in={self.retry_interval:g}秒，"
                    f"error={type(error).__name__}: {error}"
                )
                time.sleep(self.retry_interval)

    def _reset_pagination_stats(self) -> None:
        """清空当前一轮更新的分页汇总计数。"""
        with self._pagination_lock:
            self._pagination_stats = {
                "calls": 0,
                "requests": 0,
                "pages": 0,
                "multi_page": 0,
                "rows": 0,
                "extra_rows": 0,
                "samples": 0,
            }

    def _record_pagination(
            self,
            *,
            request_count: int,
            page_count: int,
            row_count: int,
            extra_rows: int,
    ) -> bool:
        """累计一次分页请求，并返回是否输出 INFO 样例。"""
        with self._pagination_lock:
            stats = self._pagination_stats
            stats["calls"] += 1
            stats["requests"] += request_count
            stats["pages"] += page_count
            stats["rows"] += row_count
            stats["extra_rows"] += extra_rows
            if page_count <= 1:
                return False
            stats["multi_page"] += 1
            if stats["samples"] >= _MAX_PAGINATION_LOG_SAMPLES:
                return False
            stats["samples"] += 1
            return True

    def _pagination_summary(self) -> str:
        """返回适合追加到 Worker 汇总日志的分页信息。"""
        with self._pagination_lock:
            stats = dict(self._pagination_stats)
        if not stats["calls"]:
            return ""
        omitted = max(stats["multi_page"] - stats["samples"], 0)
        omitted_text = (
            f"，省略明细={omitted:,}"
            if omitted
            else ""
        )
        return (
            f"，分页完成={stats['calls']:,}，"
            f"多页={stats['multi_page']:,}，"
            f"请求={stats['requests']:,}，"
            f"有效页={stats['pages']:,}，"
            f"返回行={stats['rows']:,}，"
            f"补齐行={stats['extra_rows']:,}{omitted_text}"
        )

    def fetch_paginated(
            self,
            endpoint: Callable[..., pd.DataFrame | None],
            *,
            params: Mapping[str, object],
            page_size: int,
            context: str,
            stop_on_short: bool = False,
            max_pages: int = 10_000,
    ) -> pd.DataFrame:
        """通过 ``limit/offset`` 获取完整响应，并逐页限流和重试。

        所有页面合并后原样返回，不在这里清洗或去重。默认以空页作为结束
        信号；已确认接口严格遵守 ``page_size`` 时，可通过
        ``stop_on_short=True`` 在不足一页时提前结束。
        """
        if page_size <= 0:
            raise ValueError("page_size 必须大于 0")
        if max_pages <= 0:
            raise ValueError("max_pages 必须大于 0")

        request_params = dict(params)
        if {"limit", "offset"} & request_params.keys():
            raise ValueError("params 不能包含 limit 或 offset")

        pages: list[pd.DataFrame] = []
        expected_columns: tuple[object, ...] | None = None
        seen_pages: set[tuple[tuple[object, ...], bytes]] = set()
        empty_result: pd.DataFrame | None = None
        started = time.perf_counter()
        request_count = 0
        stop_reason = ""
        offset = 0

        for page_number in range(1, max_pages + 1):
            current_offset = offset

            def request_page() -> pd.DataFrame:
                nonlocal request_count
                request_count += 1
                result = endpoint(
                    **request_params,
                    limit=page_size,
                    offset=current_offset,
                )
                if not isinstance(result, pd.DataFrame):
                    raise TypeError(
                        f"{context} 分页响应不是 DataFrame："
                        f"{type(result).__name__}"
                    )
                return result

            page = self.retry(
                request_page,
                context=(
                    f"{context} 第 {page_number} 页"
                    f"[offset={current_offset}, limit={page_size}]"
                ),
            )

            if page.empty:
                empty_result = page
                stop_reason = "空页"
                break

            page = page.reset_index(drop=True)
            columns = tuple(page.columns)
            if expected_columns is None:
                expected_columns = columns
            elif columns != expected_columns:
                raise ValueError(
                    f"{context} 第 {page_number} 页字段发生变化："
                    f"{list(columns)} != {list(expected_columns)}"
                )

            # 忽略行顺序识别服务端重复返回的页面，避免 offset 失效后死循环。
            hashes = pd.util.hash_pandas_object(
                page,
                index=False,
            ).to_numpy()
            signature = (columns, np.sort(hashes).tobytes())
            if signature in seen_pages:
                raise RuntimeError(
                    f"{context} 第 {page_number} 页内容重复，"
                    "offset 可能未生效"
                )
            seen_pages.add(signature)

            pages.append(page)
            offset += len(page)
            if stop_on_short and len(page) < page_size:
                stop_reason = "短页"
                break
        else:
            raise RuntimeError(
                f"{context} 已达到最大分页数 {max_pages:,}，"
                "结果可能仍未完整"
            )

        if pages:
            result = pd.concat(pages, ignore_index=True)
        elif empty_result is not None:
            result = empty_result
        else:
            result = pd.DataFrame()
        page_count = len(pages)
        total_rows = sum(map(len, pages))
        first_page_rows = len(pages[0]) if pages else 0
        extra_rows = total_rows - first_page_rows
        is_info_sample = self._record_pagination(
            request_count=request_count,
            page_count=page_count,
            row_count=total_rows,
            extra_rows=extra_rows,
        )
        if request_count > 1:
            elapsed = time.perf_counter() - started
            message = (
                f"{context} 分页完成：请求={request_count:,}，"
                f"有效页={page_count:,}，原始行={total_rows:,}，"
                f"补齐行={extra_rows:,}，"
                f"停止={stop_reason or '未知'}，耗时={elapsed:.2f}秒"
            )
            if is_info_sample:
                logger.info(message)
            elif page_count <= 1:
                logger.debug(message)

        return result

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
        self._partial_write_rows = 0
        batch_count = (len(data) + self.batch_size - 1) // self.batch_size
        # fetch_all 已保证返回契约；此处只控制网络批次，不再处理内容。
        for batch_number, offset in enumerate(
                range(0, len(data), self.batch_size),
                start=1,
        ):
            batch = data.iloc[offset:offset + self.batch_size]
            written = writer.append(batch)
            total += written
            self._partial_write_rows = total
            logger.debug(
                f"{self} 写入批次 {batch_number:,}/{batch_count:,}："
                f"提交={len(batch):,}行，实际写入={written:,}行，"
                f"本次累计={total:,}行"
            )
        self._partial_write_rows = 0
        return total

    def run(self) -> int:
        """执行完整增量更新并返回成功写入 DolphinDB 的总行数。"""
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
            f"限速={throttle_text}，批量={self.batch_size:,}行"
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
            total += self._partial_write_rows
            self._partial_write_rows = 0
            elapsed = time.perf_counter() - started
            logger.exception(
                f"{name} 更新失败：已确认写入={total:,}行，"
                f"当前缓冲={rows:,}行，耗时={elapsed:.2f}秒，"
                f"error={type(error).__name__}: {error}"
            )
            raise

        elapsed = time.perf_counter() - started
        throughput = total / elapsed if elapsed > 0 else 0.0
        logger.success(
            f"{name} 更新完成：写入={total:,}行，耗时={elapsed:.2f}秒，"
            f"吞吐={throughput:,.0f}行/秒"
        )
        return total

    def __repr__(self) -> str:
        """返回与日志标识一致的调试字符串。"""
        return str(self)
