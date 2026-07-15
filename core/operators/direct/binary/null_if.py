"""binary.null_if 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectBinaryNullIfParams(StrictModel):
    """binary.null_if 不接收参数。"""


class DirectBinaryNullIfOperator(DirectOperator):
    """相等时返回 NULL。"""

    op: Literal['binary.null_if'] = Field(..., description='相等时返回 NULL。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinaryNullIfParams = Field(
        default_factory=DirectBinaryNullIfParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'ANY'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_binary_null_if(left, right) {
            /*
            逐元素比较两个操作数；相等时返回 NULL，否则返回 left。

            当一侧为标量、另一侧为向量时，标量按元素广播；两个向量输入必须长度一致。

            该算符常用于把特定哨兵值替换为 NULL；未匹配的位置保持 left 的原始类型和值。

            Parameters
            ----------
            left : scalar or vector
                左操作数。
            right : scalar or vector
                右操作数。

            Returns
            -------
            result : scalar or vector
                结果类型和形状由输入与算符语义决定。

            Examples
            --------
            >>> left = 1 2 3 4
            >>> right = 0 2 0 4
            >>> direct_binary_null_if(left, right)
            [1, NULL, 3, NULL]
            */
            return iif(left == right, NULL, left)
        }
        """
    )
