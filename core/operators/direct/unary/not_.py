"""unary.not 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryNotParams(StrictModel):
    """unary.not 不接收参数。"""


class DirectUnaryNotOperator(DirectOperator):
    """逐行逻辑非。"""

    op: Literal['unary.not'] = Field(..., description='逐行逻辑非。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryNotParams = Field(
        default_factory=DirectUnaryNotParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_not(col) {
            /*
            逐元素计算逻辑非。

            Parameters
            ----------
            col : scalar or vector
                待取反的 BOOL 标量或向量。

            Returns
            -------
            result : scalar or vector[BOOL]
                布尔结果；向量输入按元素返回。

            Examples
            --------
            >>> col = true false true false
            >>> direct_unary_not(col)
            [false, true, false, true]
            */
            return !col
        }
        """
    )
