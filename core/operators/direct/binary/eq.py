"""binary.eq 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectBinaryEqParams(StrictModel):
    """binary.eq 不接收参数。"""


class DirectBinaryEqOperator(DirectOperator):
    """逐行比较 eq。"""

    op: Literal['binary.eq'] = Field(..., description='逐行比较 eq。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinaryEqParams = Field(
        default_factory=DirectBinaryEqParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_binary_eq(left, right) {
            /*
            逐元素判断 left 是否等于 right。

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
            >>> left = 1.0 2.0 4.0
            >>> right = 3.0 2.0 1.0
            >>> direct_binary_eq(left, right)
            [false, true, false]
            */
            return left == right
        }
        """
    )
