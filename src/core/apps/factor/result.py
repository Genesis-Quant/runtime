"""定义持有 DolphinDB 服务端因子分析表的惰性结果对象。"""

from collections.abc import Mapping
from typing import Any

import pandas as pd

from core.utils import SessionResult

from .schema import FactorAnalysisParameters


class FactorAnalysisResult(SessionResult):
    """按需下载预处理因子、IC 和分组收益表。"""

    def __init__(
        self,
        *,
        session: Any,
        parameters: FactorAnalysisParameters,
        information_coefficient_refs: Mapping[str, str],
        group_return_refs: Mapping[str, str],
    ) -> None:
        super().__init__(session=session)
        self.parameters = parameters
        self.factor_columns = tuple(parameters.factor_columns)
        self.return_columns = tuple(parameters.return_columns)
        self.information_coefficient_refs = dict(
            information_coefficient_refs
        )
        self.group_return_refs = dict(group_return_refs)

    def _reference(
        self,
        factor: str,
        references: Mapping[str, str],
    ) -> str:
        """校验因子名并返回对应服务端变量名。"""
        try:
            return references[factor]
        except KeyError as error:
            raise KeyError(
                f"未知因子 {factor!r}；可选值："
                f"{list(self.factor_columns)}"
            ) from error

    @property
    def processed_data(self) -> pd.DataFrame:
        """下载内置预处理或 DSL 手动预处理后的完整因子表。"""
        return self.download("coreFactorProcessedData")

    def information_coefficient(self, factor: str) -> pd.DataFrame:
        """下载指定因子的 IC 与 Rank IC 时间序列表。"""
        return self.download(
            self._reference(
                factor,
                self.information_coefficient_refs,
            )
        )

    def group_returns(self, factor: str) -> pd.DataFrame:
        """下载指定因子的市值加权分组收益时间序列表。"""
        return self.download(
            self._reference(factor, self.group_return_refs)
        )

    @property
    def information_coefficients(
        self,
    ) -> dict[str, pd.DataFrame]:
        """下载全部因子的 IC 与 Rank IC 表。"""
        return {
            factor: self.information_coefficient(factor)
            for factor in self.factor_columns
        }

    @property
    def all_group_returns(self) -> dict[str, pd.DataFrame]:
        """下载全部因子的分组收益表。"""
        return {
            factor: self.group_returns(factor)
            for factor in self.factor_columns
        }


__all__ = ["FactorAnalysisResult"]
