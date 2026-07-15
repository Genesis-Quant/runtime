"""unary.asin 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryAsinParams(StrictModel):
    """unary.asin 不接收参数。"""


class DirectUnaryAsinOperator(DirectOperator):
    """逐行执行 asin。"""

    op: Literal['unary.asin'] = Field(..., description='逐行执行 asin。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryAsinParams = Field(
        default_factory=DirectUnaryAsinParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_asin(col) {
            /*
            逐元素计算反正弦，输入值必须位于 [-1, 1]。

            Parameters
            ----------
            col : scalar or vector
                待计算的标量或向量。

            Returns
            -------
            result : scalar or vector[NUMBER]
                数值结果；向量输入按元素返回。

            Examples
            --------
            >>> col = -1.0 -0.5 0.0 0.5 1.0
            >>> direct_unary_asin(col)
            [-1.5708, -0.523599, 0, 0.523599, 1.5708]
            */
            return asin(col)
        }
        """
    )
