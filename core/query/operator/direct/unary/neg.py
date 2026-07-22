"""unary.neg 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryNegParams(StrictModel):
    """unary.neg 不接收参数。"""


class DirectUnaryNegOperator(DirectOperator):
    """逐行执行 neg。"""

    op: Literal['unary.neg'] = Field(..., description='逐行执行 neg。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryNegParams = Field(
        default_factory=DirectUnaryNegParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_neg(col) {
            /*
            逐元素返回输入值的相反数。

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

            形状与类型：标量输入返回标量，向量输入保持长度并逐元素计算；数值类型按 DolphinDB
            对应内置函数的类型提升规则确定。

            Examples
            --------
            >>> col = -2.5 -1.0 0.0 1.5 3.2
            >>> direct_unary_neg(col)
            [2.5, 1, 0, -1.5, -3.2]

            NULL 保持在原位置：
            >>> isNull(direct_unary_neg(double([1, NULL])))
            [false, true]
            */
            return -col
        }
        """
    )
