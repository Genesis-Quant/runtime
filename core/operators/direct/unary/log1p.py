"""unary.log1p 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryLog1pParams(StrictModel):
    """unary.log1p 不接收参数。"""


class DirectUnaryLog1pOperator(DirectOperator):
    """逐行执行 log1p。"""

    op: Literal['unary.log1p'] = Field(..., description='逐行执行 log1p。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryLog1pParams = Field(
        default_factory=DirectUnaryLog1pParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_log1p(col) {
            /*
            逐元素计算 log(1 + x)，提高接近零时的数值精度。

            输入必须大于 -1；该实现比直接计算 log(1 + x) 更适合接近零的值。

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
            >>> col = 1.0 2.0 4.0 8.0
            >>> direct_unary_log1p(col)
            [0.693147, 1.09861, 1.60944, 2.19722]
            */
            return log1p(col)
        }
        """
    )
