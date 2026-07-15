"""unary.kurt 算符模型。"""

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


class CrossSectionUnaryKurtParams(StrictModel):
    """unary.kurt 不接收参数。"""


class CrossSectionUnaryKurtOperator(CrossSectionOperator):
    """按交易日广播 kurt 统计量。"""

    op: Literal['unary.kurt'] = Field(..., description='按交易日广播 kurt 统计量。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryKurtParams = Field(
        default_factory=CrossSectionUnaryKurtParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_kurt(col) {
            /*
            计算当前截面的峰度并广播结果。

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
            >>> cs_unary_kurt(col)
            [2.51036, 2.51036, 2.51036, 2.51036, 2.51036]
            */
            return broadcast_like(kurtosis(col), col)
        }
        """,
        dependencies=(BROADCAST_LIKE,)
    )
