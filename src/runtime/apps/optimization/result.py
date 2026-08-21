"""定义参数调优结果。"""

from typing import Any

import pandas as pd

from runtime.utils import SessionResult

from .schema import OptimizationAlgorithm


class OptimizationResult(SessionResult):
    """持有每种调优算法的 DolphinDB 结果表。"""

    def __init__(
            self,
            *,
            session: Any,
            table_refs: dict[OptimizationAlgorithm, str],
    ) -> None:
        super().__init__(session=session)
        self.table_refs = table_refs

    def table(self, algorithm: OptimizationAlgorithm | str) -> pd.DataFrame:
        """返回指定算法的完整重复路径与窗口元数据。"""
        name = OptimizationAlgorithm(algorithm)
        try:
            return self.download(self.table_refs[name])
        except KeyError as error:
            raise KeyError(f"调优结果不包含算法 {name.value}") from error


__all__ = ["OptimizationResult"]
