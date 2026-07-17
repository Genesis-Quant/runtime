"""unary.exp 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryExpParams(StrictModel):
    """unary.exp 不接收参数。"""


class DirectUnaryExpOperator(DirectOperator):
    """逐行执行 exp。"""

    op: Literal['unary.exp'] = Field(..., description='逐行执行 exp。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryExpParams = Field(
        default_factory=DirectUnaryExpParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_exp(col) {
            /*
            逐元素计算自然指数函数。

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
            NULL 处理：输入位置为 NULL 时，同位置结果为 NULL；本算符不做填充或缺失值替换。 exp/expm1
            的极大输入可能产生无穷值，本算符不会把无穷值自动改写为 NULL。

            形状与类型：标量输入返回标量，向量输入保持长度并逐元素计算；数值类型按 DolphinDB
            对应内置函数的类型提升规则确定。

            Examples
            --------
            >>> col = -2.5 -1.0 0.0 1.5 3.2
            >>> direct_unary_exp(col)
            [0.082085, 0.367879, 1, 4.48169, 24.5325]

            NULL 保持在原位置：
            >>> isNull(direct_unary_exp(double([1, NULL])))
            [false, true]
            */
            return exp(col)
        }
        """
    )
