"""定义写入自定义 DolphinDB 宽表的按股票 Worker。"""

from abc import ABC, abstractmethod
import time
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from core.database import create_session
from core.utils import logger

from .stock import StockWorker


class WideTableWriter:
    """复用一个 DolphinDB 会话向指定 Worker 的自定义表追加宽表数据。"""

    def __init__(self, worker: "WideWorker") -> None:
        """保存 Worker，并延迟到进入上下文时创建连接和业务表。"""
        self.worker = worker
        self.session: Any | None = None
        self.closed = False

    def open(self) -> Any:
        """确保自定义表存在并返回复用的 DolphinDB 会话。"""
        if self.closed:
            raise RuntimeError("WideTableWriter 已关闭")
        if self.session is not None:
            return self.session

        session = create_session()
        try:
            self.worker.ensure_table(session)
        except Exception:
            session.close()
            raise
        self.session = session
        logger.debug(f"{self.worker} 自定义表 Writer 已创建")
        return session

    def append(self, data: pd.DataFrame) -> int:
        """向自定义表追加一批已规范数据并返回实际提交行数。"""
        result = self.worker.check(data)
        if result.empty:
            return 0

        session = self.open()
        session.upload({"wideWorkerRows": result})
        written = int(
            session.run(
                f"tableInsert({self.worker.table}, wideWorkerRows)"
            )
        )
        if written != len(result):
            raise RuntimeError(
                f"DolphinDB 写入行数不一致："
                f"预期 {len(result):,}，实际 {written:,}"
            )
        return written

    def close(self) -> None:
        """关闭当前 Writer 持有的 DolphinDB 会话。"""
        if self.closed:
            return
        self.closed = True
        session = self.session
        self.session = None
        if session is not None:
            session.close()

    def __enter__(self) -> "WideTableWriter":
        """准备自定义表并返回当前 Writer。"""
        self.open()
        return self

    def __exit__(
            self,
            exc_type: Any,
            exc_value: Any,
            traceback: Any,
    ) -> None:
        """退出更新上下文时关闭 DolphinDB 会话。"""
        self.close()


class WideWorker(StockWorker, ABC):
    """按股票并发获取数据，并写入子类声明的自定义宽表。"""

    COLUMNS: ClassVar[tuple[str, ...]] = ()
    KEY_COLUMN: ClassVar[str] = ""
    DATE_COLUMN: ClassVar[str] = ""
    TABLE: ClassVar[str] = ""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """校验自定义表契约后初始化按股票更新流程。"""
        if not self.COLUMNS:
            raise TypeError(f"{self}.COLUMNS 不能为空")
        if self.KEY_COLUMN not in self.COLUMNS:
            raise TypeError(
                f"{self}.KEY_COLUMN {self.KEY_COLUMN!r} 不在 COLUMNS 中"
            )
        if self.DATE_COLUMN not in self.COLUMNS:
            raise TypeError(
                f"{self}.DATE_COLUMN {self.DATE_COLUMN!r} 不在 COLUMNS 中"
            )
        if not self.TABLE:
            raise TypeError(f"{self}.TABLE 不能为空")
        super().__init__(*args, **kwargs)

    @property
    def fields(self) -> tuple[str, ...]:
        """返回自定义宽表的固定列。"""
        return self.COLUMNS

    @property
    def table(self) -> str:
        """返回当前 Worker 的 DolphinDB 目标表表达式。"""
        return self.TABLE

    @abstractmethod
    def ensure_table(self, session: Any) -> None:
        """使用已有会话确保子类的自定义表存在。"""
        raise NotImplementedError

    def create_writer(self) -> WideTableWriter:
        """返回写入当前自定义宽表的会话写入器。"""
        return WideTableWriter(self)

    def check(self, data: pd.DataFrame) -> pd.DataFrame:
        """校验宽表结果的列顺序及增量日期列类型。"""
        if not isinstance(data, pd.DataFrame):
            raise TypeError("fetch_one 结果必须是 DataFrame")
        if tuple(data.columns) != self.COLUMNS:
            raise ValueError(
                "fetch_one 结果列必须严格为 "
                f"{list(self.COLUMNS)}，实际为 {list(data.columns)}"
            )
        if not pd.api.types.is_datetime64_any_dtype(
                data[self.DATE_COLUMN]
        ):
            raise ValueError(
                f"fetch_one 结果的 {self.DATE_COLUMN} "
                "列必须为 datetime64 类型"
            )
        return data

    def get_last_dates(self) -> dict[str, pd.Timestamp]:
        """按股票返回自定义表中增量日期列的最近日期。"""
        started = time.perf_counter()
        logger.debug(
            f"{self} 查询 {len(self.codes):,} 只股票的最近数据日"
        )
        session = create_session()
        try:
            self.ensure_table(session)
            session.upload(
                {"wideWorkerCodes": np.asarray(self.codes, dtype=str)}
            )
            result = session.run(
                f"""
                select
                    {self.KEY_COLUMN},
                    max({self.DATE_COLUMN}) as {self.DATE_COLUMN}
                from {self.table}
                where {self.KEY_COLUMN} in symbol(wideWorkerCodes)
                group by {self.KEY_COLUMN}
                """
            )
        finally:
            session.close()

        dates = (
            {
                str(getattr(row, self.KEY_COLUMN)): pd.Timestamp(
                    getattr(row, self.DATE_COLUMN)
                ).normalize()
                for row in result.itertuples(index=False)
                if not pd.isna(getattr(row, self.DATE_COLUMN))
            }
            if result is not None and not result.empty
            else {}
        )
        elapsed = time.perf_counter() - started
        range_text = (
            f"{min(dates.values()):%Y-%m-%d} 至 "
            f"{max(dates.values()):%Y-%m-%d}"
            if dates
            else "无"
        )
        logger.info(
            f"{self} 增量基线：覆盖={len(dates):,}/"
            f"{len(self.codes):,}，最近数据日={range_text}，"
            f"查询耗时={elapsed:.2f}秒"
        )
        return dates


__all__ = ["WideWorker"]
