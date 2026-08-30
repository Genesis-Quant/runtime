"""定义持有 DolphinDB 服务端因子预处理表的惰性结果对象。"""

from typing import Any

import pandas as pd

from runtime.utils import SessionResult, logger

from .schema import FactorAnalysisParameters


class FactorAnalysisResult(SessionResult):
    """按需下载预处理因子并计算全部因子的分析表。"""

    def __init__(
            self,
            *,
            session: Any,
            parameters: FactorAnalysisParameters,
            processed_ref: str,
    ) -> None:
        super().__init__(session=session)
        self.parameters = parameters
        self.factor_columns = tuple(parameters.factor_columns)
        self.return_columns = tuple(parameters.return_columns)
        self.processed_ref = processed_ref

    @property
    def processed_data(self) -> pd.DataFrame:
        """下载内置预处理或 DSL 手动预处理后的完整因子表。"""
        return self.download(self.processed_ref)

    @property
    def information_coefficient(self) -> pd.DataFrame:
        """计算全部因子的 IC，并按 time 横向拼接。"""
        logger.info("session.run: 计算全部因子的 IC")
        return self.download(f"""
            factor::factorInformationCoefficient(
                {self.processed_ref},
                coreFactorReturnColumns,
                coreFactorColumns,
                "time"
            )
        """)

    @property
    def group_returns(self) -> pd.DataFrame:
        """计算全部因子的分组收益，并按 time 横向拼接。"""
        logger.info("session.run: 计算全部因子的分组收益")
        return self.download(f"""
            factor::factorGroupReturns(
                {self.processed_ref},
                coreFactorReturnColumns,
                coreFactorColumns,
                coreFactorGroupCount,
                coreFactorSelectionCount,
                "time",
                "code",
                coreFactorMarketValueColumn
            )
        """)

    @property
    def diagnostics(self) -> pd.DataFrame:
        """在服务端聚合逐日样本覆盖和分组占用诊断。"""
        logger.info("session.run: 计算因子样本与分组诊断")
        return self.download(f"""
            factor::factorDiagnostics(
                {self.processed_ref},
                coreFactorReturnColumns,
                coreFactorColumns,
                coreFactorGroupCount,
                "time",
                "code",
                coreFactorMarketValueColumn
            )
        """)


__all__ = ["FactorAnalysisResult"]
