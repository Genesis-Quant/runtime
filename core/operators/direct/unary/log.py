"""unary.log 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryLogParams(StrictModel):
    """unary.log 不接收参数。"""


class DirectUnaryLogOperator(DirectOperator):
    """逐行执行 log。"""

    op: Literal['unary.log'] = Field(..., description='逐行执行 log。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryLogParams = Field(
        default_factory=DirectUnaryLogParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_log(col) {
            /*
            逐元素计算自然对数。

            输入必须为正数；不满足定义域的位置由 DolphinDB 返回 NULL。

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
            >>> direct_unary_log(col)
            [0, 0.693147, 1.38629, 2.07944]
            */
            return log(col)
        }
        """
    )
