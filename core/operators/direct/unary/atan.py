"""unary.atan 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryAtanParams(StrictModel):
    """unary.atan 不接收参数。"""


class DirectUnaryAtanOperator(DirectOperator):
    """逐行执行 atan。"""

    op: Literal['unary.atan'] = Field(..., description='逐行执行 atan。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryAtanParams = Field(
        default_factory=DirectUnaryAtanParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_atan(col) {
            /*
            逐元素计算反正切。

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
            NULL 处理：输入位置为 NULL 时，同位置结果为 NULL；本算符不做填充或缺失值替换。

            形状与类型：标量输入返回标量，向量输入保持长度并逐元素计算；反正切结果以弧度返回，范围为 (-pi/2,
            pi/2)。

            Examples
            --------
            >>> col = -2.5 -1.0 0.0 1.5 3.2
            >>> direct_unary_atan(col)
            [-1.19029, -0.785398, 0, 0.982794, 1.26791]

            NULL 保持在原位置：
            >>> isNull(direct_unary_atan(double([1, NULL])))
            [false, true]
            */
            return atan(col)
        }
        """
    )
