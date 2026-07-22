"""unary.asin 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryAsinParams(StrictModel):
    """unary.asin 不接收参数。"""


class DirectUnaryAsinOperator(DirectOperator):
    """逐行执行 asin。"""

    op: Literal['unary.asin'] = Field(..., description='逐行执行 asin。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryAsinParams = Field(
        default_factory=DirectUnaryAsinParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_asin(col) {
            /*
            逐元素计算反正弦，输入值必须位于 [-1, 1]。

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
            NULL 处理：有效定义域为 [-1, 1]；超出定义域的有限值与 NULL 都返回
            NULL。函数不会填充、删除或重排输入位置。

            形状与数值：标量输入返回标量，向量输入保持长度并逐元素计算。结果使用 DolphinDB
            浮点数学函数的精度和溢出规则。

            Examples
            --------
            >>> col = -1.0 -0.5 0.0 0.5 1.0
            >>> direct_unary_asin(col)
            [-1.5708, -0.523599, 0, 0.523599, 1.5708]

            非法定义域和 NULL 都产生缺失结果：
            >>> isNull(direct_unary_asin(double([-2, NULL, 1])))
            [true, true, false]
            */
            return asin(col)
        }
        """
    )
