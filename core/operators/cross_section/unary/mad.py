"""unary.mad 算符模型。"""

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


class CrossSectionUnaryMadParams(StrictModel):
    """unary.mad 不接收参数。"""


class CrossSectionUnaryMadOperator(CrossSectionOperator):
    """按交易日广播 mad 统计量。"""

    op: Literal['unary.mad'] = Field(..., description='按交易日广播 mad 统计量。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryMadParams = Field(
        default_factory=CrossSectionUnaryMadParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_mad(col) {
            /*
            计算当前截面的平均绝对离差并广播结果。

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
            >>> cs_unary_mad(col)
            [1, 1, 1, 1, 1]
            */
            return broadcast_like(mad(col, true), col)
        }
        """,
        dependencies=(BROADCAST_LIKE,)
    )
