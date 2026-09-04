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
            source_ref: str,
            computed_ref: str,
            filtered_ref: str,
            processed_ref: str,
    ) -> None:
        super().__init__(session=session)
        self.parameters = parameters
        self.factor_columns = tuple(parameters.factor_columns)
        self.return_columns = tuple(parameters.return_columns)
        self.source_ref = source_ref
        self.computed_ref = computed_ref
        self.filtered_ref = filtered_ref
        self.processed_ref = processed_ref

    @property
    def execution_statistics(self) -> pd.DataFrame:
        """按交易日统计原始股票数及各过滤阶段剩余股票数。"""
        logger.info("session.run: 统计 DSL 各过滤阶段的股票数量")
        return self.download(f"""
            factor::factorExecutionStatistics(
                {self.source_ref},
                {self.computed_ref},
                {self.filtered_ref},
                coreDslFilters,
                coreOutputStart,
                coreOutputEnd,
                "time",
                "code"
            )
        """)

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
    def group_turnover(self) -> pd.DataFrame:
        """计算各收益持有期的分组换手率与因子秩自相关。"""
        logger.info("session.run: 计算全部因子的分组换手率")
        return self.download(f"""
            factor::factorGroupTurnover(
                {self.processed_ref},
                coreFactorColumns,
                coreFactorTurnoverPeriods,
                coreFactorGroupCount,
                coreFactorSelectionCount,
                "time",
                "code"
            )
        """)


__all__ = ["FactorAnalysisResult"]
