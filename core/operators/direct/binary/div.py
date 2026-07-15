"""binary.div 算符模型。"""

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


class DirectBinaryDivParams(StrictModel):
    """binary.div 不接收参数。"""


class DirectBinaryDivOperator(DirectOperator):
    """逐行执行 div。"""

    op: Literal['binary.div'] = Field(..., description='逐行执行 div。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinaryDivParams = Field(
        default_factory=DirectBinaryDivParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_binary_div(left, right) {
            /*
            逐元素计算 left 除以 right；除数为零的位置返回 NULL。

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
            >>> direct_binary_div(left, right)
            [2.5, 2.66667, 2.75]

            >>> left = 5.0 8.0 11.0
            >>> right = 2.0 0.0 4.0

            除数为零的位置返回 NULL：
            >>> direct_binary_div(left, right)
            [2.5, NULL, 2.75]
            */
            return divide_or_null(left, right)
        }
        """,
        dependencies=(DIVIDE_OR_NULL,)
    )
