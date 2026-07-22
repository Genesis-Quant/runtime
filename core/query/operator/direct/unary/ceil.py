"""unary.ceil 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryCeilParams(StrictModel):
    """unary.ceil 不接收参数。"""


class DirectUnaryCeilOperator(DirectOperator):
    """逐行执行 ceil。"""

    op: Literal['unary.ceil'] = Field(..., description='逐行执行 ceil。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryCeilParams = Field(
        default_factory=DirectUnaryCeilParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_ceil(col) {
            /*
            逐元素向正无穷方向取整。

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

            形状与类型：标量输入返回标量，向量输入保持长度并逐元素计算；结果按对应方向取整，但仍遵循 DolphinDB
            内置函数的返回 dtype。

            Examples
            --------
            >>> col = -2.5 -1.0 0.0 1.5 3.2
            >>> direct_unary_ceil(col)
            [-2, -1, 0, 2, 4]

            NULL 保持在原位置：
            >>> isNull(direct_unary_ceil(double([1, NULL])))
            [false, true]
            */
            return ceil(col)
        }
        """
    )
