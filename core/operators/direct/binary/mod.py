"""binary.mod 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    DIVIDE_OR_NULL,
)

from core.operators.base import DirectOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectBinaryModParams(StrictModel):
    """binary.mod 不接收参数。"""


class DirectBinaryModOperator(DirectOperator):
    """逐行执行 mod。"""

    op: Literal['binary.mod'] = Field(..., description='逐行执行 mod。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinaryModParams = Field(
        default_factory=DirectBinaryModParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_binary_mod(left, right) {
            /*
            逐元素计算 left 除以 right 的余数；除数为零的位置返回 NULL。

            当一侧为标量、另一侧为向量时，标量按元素广播；两个向量输入必须长度一致。

            right 为 0 或 NULL 的位置不执行运算，结果显式设为 NULL。

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
            >>> left = 5.0 8.0 11.0
            >>> right = 2.0 3.0 4.0
            >>> direct_binary_mod(left, right)
            [1, 2, 3]

            >>> left = 5.0 8.0 11.0
            >>> right = 2.0 0.0 4.0

            除数为零的位置返回 NULL：
            >>> direct_binary_mod(left, right)
            [1, NULL, 3]
            */
            return left - floor(divide_or_null(left, right)) * right
        }
        """,
        dependencies=(DIVIDE_OR_NULL,)
    )
