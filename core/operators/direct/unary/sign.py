"""unary.sign 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnarySignParams(StrictModel):
    """unary.sign 不接收参数。"""


class DirectUnarySignOperator(DirectOperator):
    """逐行执行 sign。"""

    op: Literal['unary.sign'] = Field(..., description='逐行执行 sign。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnarySignParams = Field(
        default_factory=DirectUnarySignParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_sign(col) {
            /*
            逐元素返回负数、零和正数对应的 -1、0 和 1。

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

            形状与类型：标量输入返回标量，向量输入保持长度并逐元素计算；有效输入分别映射为 -1、0 或 1。

            Examples
            --------
            >>> col = -2.5 -1.0 0.0 1.5 3.2
            >>> direct_unary_sign(col)
            [-1, -1, 0, 1, 1]

            NULL 保持在原位置：
            >>> isNull(direct_unary_sign(double([1, NULL])))
            [false, true]
            */
            return signum(col)
        }
        """
    )
