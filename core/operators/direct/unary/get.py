"""unary.get 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryGetParams(StrictModel):
    """unary.get 不接收参数。"""


class DirectUnaryGetOperator(DirectOperator):
    """原样返回操作数。"""

    op: Literal['unary.get'] = Field(..., description='原样返回操作数。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryGetParams = Field(
        default_factory=DirectUnaryGetParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'ANY'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_get(col) {
            /*
            原样返回已经求值的操作数。

            Parameters
            ----------
            col : scalar or vector
                待计算的标量或向量。

            Returns
            -------
            result : scalar or vector
                与 col 完全相同的类型、形状和值。

            Notes
            -----
            NULL 处理：输入按原值返回，NULL 的类型、位置和数量全部保持不变。

            形状与类型：这是恒等算符，不复制业务语义、不转换 dtype，也不对标量进行隐式广播。

            Examples
            --------
            >>> col = -2.5 -1.0 0.0 1.5 3.2
            >>> direct_unary_get(col)
            [-2.5, -1, 0, 1.5, 3.2]

            NULL 保持在原位置：
            >>> isNull(direct_unary_get(double([1, NULL])))
            [false, true]
            */
            return col
        }
        """
    )
