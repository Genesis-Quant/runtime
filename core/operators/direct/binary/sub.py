"""binary.sub 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectBinarySubParams(StrictModel):
    """binary.sub 不接收参数。"""


class DirectBinarySubOperator(DirectOperator):
    """逐行执行 sub。"""

    op: Literal['binary.sub'] = Field(..., description='逐行执行 sub。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinarySubParams = Field(
        default_factory=DirectBinarySubParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_binary_sub(left, right) {
            /*
            逐元素计算 left 减去 right。

            当一侧为标量、另一侧为向量时，标量按元素广播；两个向量输入必须长度一致。

            Parameters
            ----------
            left : scalar or vector
                左操作数。
            right : scalar or vector
                右操作数。

            Returns
            -------
            result : scalar or vector[NUMBER]
                数值结果；向量输入按元素返回。

            Examples
            --------
            >>> left = 1.0 2.0 4.0
            >>> right = 3.0 2.0 1.0
            >>> direct_binary_sub(left, right)
            [-2, 0, 3]
            */
            return left - right
        }
        """
    )
