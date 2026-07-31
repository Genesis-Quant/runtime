"""定义持有 DolphinDB DOS 结果脚本的惰性查询结果。"""
from typing import Any

import pandas as pd

from core.utils import SessionResult


class QueryResult(SessionResult):
    """按需下载统一因子查询的服务端结果表。"""

    def __init__(
            self,
            *,
            session: Any,
            source_ref: str,
            computed_ref: str,
            filtered_ref: str,
            data_ref: str,
    ):
        super().__init__(session=session)
        self.source_ref = source_ref
        self.computed_ref = computed_ref
        self.filtered_ref = filtered_ref
        self.data_ref = data_ref

    @property
    def source_data(self) -> pd.DataFrame:
        """访问时下载用于 compute 的原始因子表"""
        return self.download(self.source_ref)

    @property
    def computed_data(self) -> pd.DataFrame:
        """访问时下载应用 filters 之前的 DSL 因子表。"""
        return self.download(self.computed_ref)

    @property
    def filtered_data(self) -> pd.DataFrame:
        """访问时下载应用 filters 之后的 DSL 因子表。"""
        return self.download(self.filtered_ref)

    @property
    def data(self) -> pd.DataFrame:
        """访问时下载最终投影和筛选后的结果表。"""
        return self.download(self.data_ref)


__all__ = ["QueryResult"]
