"""binary.add 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectBinaryAddParams(StrictModel):
    """binary.add 不接收参数。"""


class DirectBinaryAddOperator(DirectOperator):
    """逐行执行 add。"""

    op: Literal['binary.add'] = Field(..., description='逐行执行 add。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinaryAddParams = Field(
        default_factory=DirectBinaryAddParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_binary_add(left, right) {
            /*
            逐元素计算 left 与 right 的和。标量按 DolphinDB 广播规则参与运算。

            当一侧为标量、另一侧为向量时，标量按元素广播；两个向量输入必须长度一致。

            Parameters
            ----------
            left : scalar or vector
                被加数；标量或与 right 等长的数值向量。
            right : scalar or vector
                加数；标量或与 left 等长的数值向量。

            Returns
            -------
            result : scalar or vector[NUMBER]
                数值结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：任一操作数在某位置为 NULL 时，该位置结果为 NULL；本算符不会跳过缺失值。

            广播与类型：标量可与向量逐元素广播，两个向量必须等长；结果 dtype 使用 DolphinDB
            的数值类型提升规则。

            Examples
            --------
            >>> left = 1.0 2.0 4.0
            >>> right = 3.0 2.0 1.0
            >>> direct_binary_add(left, right)
            [4, 4, 5]

            任一侧为 NULL 时传播缺失：
            >>> isNull(direct_binary_add(double([1, NULL]), double([2, 3])))
            [false, true]
            */
            return left + right
        }
        """
    )
