"""unary.max 算符模型。"""

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


class CrossSectionUnaryMaxParams(StrictModel):
    """unary.max 不接收参数。"""


class CrossSectionUnaryMaxOperator(CrossSectionOperator):
    """按交易日广播 max 统计量。"""

    op: Literal['unary.max'] = Field(..., description='按交易日广播 max 统计量。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryMaxParams = Field(
        default_factory=CrossSectionUnaryMaxParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_max(col) {
            /*
            计算当前截面的最大值并广播结果。

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
            >>> cs_unary_max(col)
            [8, 8, 8, 8, 8]
            */
            return broadcast_like(max(col), col)
        }
        """,
        dependencies=(BROADCAST_LIKE,)
    )
