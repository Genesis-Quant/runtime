"""grouped.demean 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import CrossSectionOperator
from core.operators.fields import GroupedFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionGroupedDemeanParams(StrictModel):
    """grouped.demean 不接收参数。"""


class CrossSectionGroupedDemeanOperator(CrossSectionOperator):
    """按交易日和分类键执行 demean。"""

    op: Literal['grouped.demean'] = Field(..., description='按交易日和分类键执行 demean。')
    fields: GroupedFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionGroupedDemeanParams = Field(
        default_factory=CrossSectionGroupedDemeanParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_grouped_demean(col) {
            /*
            在当前分类组内减去组均值。

            计算只使用传入的当前分类组，返回向量与 col 等长。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Notes
            -----
            NULL 处理：组均值忽略 NULL，但减法会保留原输入的 NULL，因此缺失位置的结果仍为 NULL。

            分组内语义：每组只减去本组均值，不使用其他组观测，也不做尺度标准化。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0
            >>> cs_grouped_demean(col)
            [-2.4, -1.4, -1.4, 0.6, 4.6]

            均值跳过 NULL，但缺失位置仍缺失：
            >>> cs_grouped_demean(double([1, NULL, 3]))
            [-1, NULL, 1]
            */
            return col - avg(col)
        }
        """
    )
