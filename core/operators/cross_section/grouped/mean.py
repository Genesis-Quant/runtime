"""grouped.mean 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    BROADCAST_LIKE,
)

from core.operators.base import CrossSectionOperator
from core.operators.fields import GroupedFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionGroupedMeanParams(StrictModel):
    """grouped.mean 不接收参数。"""


class CrossSectionGroupedMeanOperator(CrossSectionOperator):
    """按交易日和分类键执行 mean。"""

    op: Literal['grouped.mean'] = Field(..., description='按交易日和分类键执行 mean。')
    fields: GroupedFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionGroupedMeanParams = Field(
        default_factory=CrossSectionGroupedMeanParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_grouped_mean(col) {
            /*
            计算当前分类组的均值，并把该值广播到组内各观测。

            计算只使用传入的当前分类组，返回向量与 col 等长。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0
            >>> cs_grouped_mean(col)
            [3.4, 3.4, 3.4, 3.4, 3.4]
            */
            return broadcast_like(avg(col), col)
        }
        """,
        dependencies=(BROADCAST_LIKE,)
    )
