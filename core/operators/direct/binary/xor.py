"""binary.xor 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectBinaryXorParams(StrictModel):
    """binary.xor 不接收参数。"""


class DirectBinaryXorOperator(DirectOperator):
    """逐行逻辑 xor。"""

    op: Literal['binary.xor'] = Field(..., description='逐行逻辑 xor。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinaryXorParams = Field(
        default_factory=DirectBinaryXorParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_binary_xor(left, right) {
            /*
            逐元素计算 left 与 right 的逻辑异或。

            当一侧为标量、另一侧为向量时，标量按元素广播；两个向量输入必须长度一致。

            Parameters
            ----------
            left : scalar or vector
                左侧 BOOL 操作数。
            right : scalar or vector
                右侧 BOOL 操作数。

            Returns
            -------
            result : scalar or vector[BOOL]
                布尔结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：任一侧为 BOOL NULL 时，该位置结果为 NULL；这里不使用 SQL 的三值短路化简，例如
            false && NULL 仍为 NULL。

            广播与类型：标量可与向量广播，输出保持输入广播后的形状且 dtype 为 BOOL。

            Examples
            --------
            >>> left = true true false false
            >>> right = true false true false
            >>> direct_binary_xor(left, right)
            [false, true, true, false]

            BOOL NULL 传播到结果：
            >>> isNull(direct_binary_xor(bool([true, NULL]), bool([false, true])))
            [false, true]
            */
            return xor(left, right)
        }
        """
    )
