"""提供带统计、重复页检测和日志的分页查询器。"""

import time
from collections.abc import Callable, Mapping
from threading import Lock

import numpy as np
import pandas as pd

from .logging import logger
from .retry import Retry


class Paginator:
    """通过 ``limit/offset`` 完整获取 DataFrame 并累计分页统计。"""

    def __init__(self, retry: Retry) -> None:
        """保存限流重试入口并初始化线程安全的统计状态。"""
        self.retry = retry
        self.lock = Lock()
        self.stats: dict[str, int] = {}
        self.reset()

    def reset(self) -> None:
        """清空当前一轮更新的分页汇总计数。"""
        with self.lock:
            self.stats = {
                "calls": 0,
                "requests": 0,
                "pages": 0,
                "multi_page": 0,
                "rows": 0,
                "extra_rows": 0,
            }

    def record(
            self,
            *,
            request_count: int,
            page_count: int,
            row_count: int,
            extra_rows: int,
    ) -> None:
        """累计一次分页查询。"""
        with self.lock:
            self.stats["calls"] += 1
            self.stats["requests"] += request_count
            self.stats["pages"] += page_count
            self.stats["rows"] += row_count
            self.stats["extra_rows"] += extra_rows
            self.stats["multi_page"] += int(page_count > 1)

    def summary(self) -> str:
        """返回适合追加到 Worker 汇总日志的分页信息。"""
        with self.lock:
            stats = dict(self.stats)
        if not stats["calls"]:
            return ""
        return (
            f"，分页完成={stats['calls']:,}，"
            f"多页={stats['multi_page']:,}，"
            f"请求={stats['requests']:,}，"
            f"有效页={stats['pages']:,}，"
            f"返回行={stats['rows']:,}，"
            f"补齐行={stats['extra_rows']:,}"
        )

    def fetch(
            self,
            endpoint: Callable[..., pd.DataFrame | None],
            *,
            params: Mapping[str, object],
            page_size: int,
            context: str,
            stop_on_short: bool = False,
            max_pages: int = 10_000,
    ) -> pd.DataFrame:
        """分页获取完整响应，所有页面原样合并，不执行清洗或去重。"""
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
                response = endpoint(
                    **request_params,
                    limit=page_size,
                    offset=current_offset,
                )
                if not isinstance(response, pd.DataFrame):
                    raise TypeError(
                        f"{context} 分页响应不是 DataFrame："
                        f"{type(response).__name__}"
                    )
                return response

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
            all_null_columns = [
                column
                for column in expected_columns or ()
                if all(page[column].isna().all() for page in pages)
            ]
            concat_pages = [page.dropna(axis="columns", how="all") for page in pages]
            result = pd.concat(concat_pages, ignore_index=True)
            for column in all_null_columns:
                result[column] = pd.concat(
                    [page[column] for page in pages],
                    ignore_index=True,
                )
            result = result.reindex(columns=expected_columns)
        elif empty_result is not None:
            result = empty_result
        else:
            result = pd.DataFrame()
        page_count = len(pages)
        total_rows = sum(map(len, pages))
        first_page_rows = len(pages[0]) if pages else 0
        extra_rows = total_rows - first_page_rows
        self.record(
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
            if page_count > 1:
                logger.info(message)
            else:
                logger.debug(message)

        return result
