"""unary.log10 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryLog10Params(StrictModel):
    """unary.log10 不接收参数。"""


class DirectUnaryLog10Operator(DirectOperator):
    """逐行执行 log10。"""

    op: Literal['unary.log10'] = Field(..., description='逐行执行 log10。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryLog10Params = Field(
        default_factory=DirectUnaryLog10Params,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_log10(col) {
            /*
            逐元素计算以 10 为底的对数。

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
            >>> direct_unary_log10(col)
            [0, 0.30103, 0.60206, 0.90309]
            */
            return log10(col)
        }
        """
    )
