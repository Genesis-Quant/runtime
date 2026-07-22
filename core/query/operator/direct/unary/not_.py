"""unary.not 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
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

            Notes
            -----
            NULL 处理：BOOL 输入为 NULL 时，逻辑取反结果仍为 NULL；不会把 NULL 当作 false。

            类型与形状：输入必须具有布尔语义，标量或向量形状保持不变。

            Examples
            --------
            >>> col = true false true false
            >>> direct_unary_not(col)
            [false, true, false, true]

            NULL 不会被当作 false：
            >>> direct_unary_not(bool([true, NULL, false]))
            [false, NULL, true]
            */
            return !col
        }
        """
    )
