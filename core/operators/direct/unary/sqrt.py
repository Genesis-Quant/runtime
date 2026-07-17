"""unary.sqrt 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnarySqrtParams(StrictModel):
    """unary.sqrt 不接收参数。"""


class DirectUnarySqrtOperator(DirectOperator):
    """逐行执行 sqrt。"""

    op: Literal['unary.sqrt'] = Field(..., description='逐行执行 sqrt。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnarySqrtParams = Field(
        default_factory=DirectUnarySqrtParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_sqrt(col) {
            /*
            逐元素计算非负输入值的平方根。

            负数不在实数平方根定义域内，对应位置返回 NULL。

            Parameters
            ----------
            col : scalar or vector
                待计算的标量或向量。

            Returns
            -------
            result : scalar or vector[NUMBER]
                数值结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：仅非负数有定义；负数与 NULL 都返回 NULL。函数不会填充、删除或重排输入位置。

            形状与数值：标量输入返回标量，向量输入保持长度并逐元素计算。结果使用 DolphinDB
            浮点数学函数的精度和溢出规则。

            Examples
            --------
            >>> col = 1.0 2.0 4.0 8.0
            >>> direct_unary_sqrt(col)
            [1, 1.41421, 2, 2.82843]

            非法定义域和 NULL 都产生缺失结果：
            >>> isNull(direct_unary_sqrt(double([-1, NULL, 4])))
            [true, true, false]
            */
            return sqrt(col)
        }
        """
    )
