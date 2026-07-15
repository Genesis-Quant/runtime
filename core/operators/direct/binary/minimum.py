"""binary.minimum 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectBinaryMinimumParams(StrictModel):
    """binary.minimum 不接收参数。"""


class DirectBinaryMinimumOperator(DirectOperator):
    """逐行执行 minimum。"""

    op: Literal['binary.minimum'] = Field(..., description='逐行执行 minimum。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinaryMinimumParams = Field(
        default_factory=DirectBinaryMinimumParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_binary_minimum(left, right) {
            /*
            逐元素返回 left 与 right 中较小的值。

            当一侧为标量、另一侧为向量时，标量按元素广播；两个向量输入必须长度一致。

            任一操作数为 NULL 的位置返回 NULL。

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
            >>> direct_binary_minimum(left, right)
            [1, 2, 1]
            */
            return iif(isNull(left) || isNull(right), NULL, iif(left <= right, left, right))
        }
        """
    )
