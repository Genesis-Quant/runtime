"""unary.floor 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectUnaryFloorParams(StrictModel):
    """unary.floor 不接收参数。"""


class DirectUnaryFloorOperator(DirectOperator):
    """逐行执行 floor。"""

    op: Literal['unary.floor'] = Field(..., description='逐行执行 floor。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectUnaryFloorParams = Field(
        default_factory=DirectUnaryFloorParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_unary_floor(col) {
            /*
            逐元素向负无穷方向取整。

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
            >>> direct_unary_floor(col)
            [-3, -1, 0, 1, 3]
            */
            return floor(col)
        }
        """
    )
