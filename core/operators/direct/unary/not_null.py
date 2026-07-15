"""unary.not_null 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryNotNullParams(StrictModel):
    """unary.not_null 不接收参数。"""


class DirectUnaryNotNullOperator(DirectOperator):
    """判断是否非空。"""

    op: Literal['unary.not_null'] = Field(..., description='判断是否非空。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryNotNullParams = Field(
        default_factory=DirectUnaryNotNullParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_not_null(col) {
            /*
            逐元素判断值是否非 NULL。

            Parameters
            ----------
            col : scalar or vector
                待计算的标量或向量。

            Returns
            -------
            result : scalar or vector[BOOL]
                布尔结果；向量输入按元素返回。

            Examples
            --------
            >>> col = 1.0 2.0 3.0
            >>> col[1] = NULL
            >>> direct_unary_not_null(col)
            [true, false, true]
            */
            return !isNull(col)
        }
        """
    )
