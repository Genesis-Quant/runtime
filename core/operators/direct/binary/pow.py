"""binary.pow 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectBinaryPowParams(StrictModel):
    """binary.pow 不接收参数。"""


class DirectBinaryPowOperator(DirectOperator):
    """逐行执行 pow。"""

    op: Literal['binary.pow'] = Field(..., description='逐行执行 pow。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinaryPowParams = Field(
        default_factory=DirectBinaryPowParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_binary_pow(left, right) {
            /*
            逐元素计算 left 的 right 次幂。

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
            >>> left = 2.0 3.0 4.0
            >>> right = 2.0 3.0 0.5
            >>> direct_binary_pow(left, right)
            [4, 27, 2]
            */
            return pow(left, right)
        }
        """
    )
