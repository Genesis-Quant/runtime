"""unary.sin 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnarySinParams(StrictModel):
    """unary.sin 不接收参数。"""


class DirectUnarySinOperator(DirectOperator):
    """逐行执行 sin。"""

    op: Literal['unary.sin'] = Field(..., description='逐行执行 sin。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnarySinParams = Field(
        default_factory=DirectUnarySinParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_sin(col) {
            /*
            逐元素计算正弦。

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

            形状与类型：标量输入返回标量，向量输入保持长度并逐元素计算；三角函数输入按弧度解释，不接受角度制标记。

            Examples
            --------
            >>> col = -2.5 -1.0 0.0 1.5 3.2
            >>> direct_unary_sin(col)
            [-0.598472, -0.841471, 0, 0.997495, -0.0583741]

            NULL 保持在原位置：
            >>> isNull(direct_unary_sin(double([1, NULL])))
            [false, true]
            */
            return sin(col)
        }
        """
    )
