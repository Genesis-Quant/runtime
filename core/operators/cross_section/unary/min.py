"""unary.min 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    BROADCAST_LIKE,
)

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryMinParams(StrictModel):
    """unary.min 不接收参数。"""


class CrossSectionUnaryMinOperator(CrossSectionOperator):
    """按交易日广播 min 统计量。"""

    op: Literal['unary.min'] = Field(..., description='按交易日广播 min 统计量。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryMinParams = Field(
        default_factory=CrossSectionUnaryMinParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_min(col) {
            /*
            计算当前截面的最小值并广播结果。

            统计时忽略 NULL，并把单个截面统计值广播为与 col 等长的向量。

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
            >>> cs_unary_min(col)
            [1, 1, 1, 1, 1]
            */
            return broadcast_like(min(col), col)
        }
        """,
        dependencies=(BROADCAST_LIKE,)
    )
