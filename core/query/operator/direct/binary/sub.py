"""binary.sub 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import BinaryFields
from core.query.operator.schema import (
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
                减法的被减数。
            right : scalar or vector
                减法的减数。

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
            >>> direct_binary_sub(left, right)
            [-2, 0, 3]

            任一侧为 NULL 时传播缺失：
            >>> isNull(direct_binary_sub(double([1, NULL]), double([2, 3])))
            [false, true]
            */
            return left - right
        }
        """
    )
