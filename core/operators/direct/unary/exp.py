"""unary.exp 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryExpParams(StrictModel):
    """unary.exp 不接收参数。"""


class DirectUnaryExpOperator(DirectOperator):
    """逐行执行 exp。"""

    op: Literal['unary.exp'] = Field(..., description='逐行执行 exp。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryExpParams = Field(
        default_factory=DirectUnaryExpParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_exp(col) {
            /*
            逐元素计算自然指数函数。

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
            >>> col = -2.5 -1.0 0.0 1.5 3.2
            >>> direct_unary_exp(col)
            [0.082085, 0.367879, 1, 4.48169, 24.5325]
            */
            return exp(col)
        }
        """
    )
