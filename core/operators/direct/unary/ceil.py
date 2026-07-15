"""unary.ceil 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
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

            Examples
            --------
            >>> col = -2.5 -1.0 0.0 1.5 3.2
            >>> direct_unary_ceil(col)
            [-2, -1, 0, 2, 4]
            */
            return ceil(col)
        }
        """
    )
