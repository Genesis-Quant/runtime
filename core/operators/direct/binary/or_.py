"""binary.or 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectBinaryOrParams(StrictModel):
    """binary.or 不接收参数。"""


class DirectBinaryOrOperator(DirectOperator):
    """逐行逻辑 or。"""

    op: Literal['binary.or'] = Field(..., description='逐行逻辑 or。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinaryOrParams = Field(
        default_factory=DirectBinaryOrParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_binary_or(left, right) {
            /*
            逐元素计算 left 与 right 的逻辑或。

            当一侧为标量、另一侧为向量时，标量按元素广播；两个向量输入必须长度一致。

            Parameters
            ----------
            left : scalar or vector
                左操作数。
            right : scalar or vector
                右操作数。

            Returns
            -------
            result : scalar or vector[BOOL]
                布尔结果；向量输入按元素返回。

            Examples
            --------
            >>> left = true true false false
            >>> right = true false true false
            >>> direct_binary_or(left, right)
            [true, true, true, false]
            */
            return left || right
        }
        """
    )
