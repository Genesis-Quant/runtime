"""unary.is_null 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryIsNullParams(StrictModel):
    """unary.is_null 不接收参数。"""


class DirectUnaryIsNullOperator(DirectOperator):
    """判断是否为空。"""

    op: Literal['unary.is_null'] = Field(..., description='判断是否为空。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryIsNullParams = Field(
        default_factory=DirectUnaryIsNullParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_is_null(col) {
            /*
            逐元素判断值是否为 NULL。

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
            >>> direct_unary_is_null(col)
            [false, true, false]
            */
            return isNull(col)
        }
        """
    )
