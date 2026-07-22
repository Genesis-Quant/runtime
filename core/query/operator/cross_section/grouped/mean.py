"""grouped.mean 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction
from core.query.dolphindb.common import (
    BROADCAST_LIKE,
)

from core.query.operator.base import CrossSectionOperator
from core.query.operator.fields import GroupedFields
from core.query.operator.schema import (
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

            Notes
            -----
            NULL 处理：组均值忽略 NULL，并把同一均值广播到组内全部位置，包括原输入为 NULL
            的位置；整组无有效值时返回 NULL。

            分组内语义：每组均值独立计算并广播，不使用其他组观测。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0
            >>> cs_grouped_mean(col)
            [3.4, 3.4, 3.4, 3.4, 3.4]

            均值会广播到原缺失位置：
            >>> cs_grouped_mean(double([1, NULL, 3]))
            [2, 2, 2]
            */
            return broadcast_like(avg(col), col)
        }
        """,
        dependencies=(BROADCAST_LIKE,)
    )
