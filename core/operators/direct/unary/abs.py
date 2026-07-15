"""unary.abs 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryAbsParams(StrictModel):
    """unary.abs 不接收参数。"""


class DirectUnaryAbsOperator(DirectOperator):
    """逐行执行 abs。"""

    op: Literal['unary.abs'] = Field(..., description='逐行执行 abs。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryAbsParams = Field(
        default_factory=DirectUnaryAbsParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_abs(col) {
            /*
            逐元素返回输入值的绝对值。

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
            >>> direct_unary_abs(col)
            [2.5, 1, 0, 1.5, 3.2]
            */
            return abs(col)
        }
        """
    )
