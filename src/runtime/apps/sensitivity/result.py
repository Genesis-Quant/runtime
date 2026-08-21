"""定义敏感性分析结果。"""

from typing import Any

import pandas as pd

from runtime.utils import SessionResult


class SensitivityResult(SessionResult):
    """持有单个 DolphinDB 敏感性分析结果表。"""

    def __init__(self, *, session: Any, table_ref: str) -> None:
        super().__init__(session=session)
        self.table_ref = table_ref

    @property
    def results(self) -> pd.DataFrame:
        """返回全部组合的参数、指标与错误。"""
        return self.download(f"select * from {self.table_ref} order by case_index")


__all__ = ["SensitivityResult"]
