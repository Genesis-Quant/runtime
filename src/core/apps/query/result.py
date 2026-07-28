"""定义持有 DolphinDB DOS 结果脚本的惰性查询结果。"""

from collections.abc import Sequence
from typing import Any

import pandas as pd

from core.utils import SessionResult

from .schema import FactorQuery


class QueryResult(SessionResult):
    """按需下载统一因子查询的服务端结果表。"""

    def __init__(
        self,
        *,
        session: Any,
        query: FactorQuery,
        output_columns: Sequence[str],
    ) -> None:
        super().__init__(session=session)
        self.query = query
        self.output_columns = tuple(output_columns)

    @property
    def data(self) -> pd.DataFrame:
        """访问时下载最终投影和筛选后的结果表。"""
        return self.download("coreQueryResultData")

    @property
    def unfiltered_data(self) -> pd.DataFrame:
        """访问时下载应用 filters 之前的 DSL 因子表。"""
        return self.download("coreQueryResultUnfilteredData")

    @property
    def filtered_data(self) -> pd.DataFrame:
        """访问时下载应用 filters 之后的 DSL 因子表。"""
        return self.download("coreQueryResultFilteredData")


__all__ = ["QueryResult"]
