"""binary.maximum 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectBinaryMaximumParams(StrictModel):
    """binary.maximum 不接收参数。"""


class DirectBinaryMaximumOperator(DirectOperator):
    """逐行执行 maximum。"""

    op: Literal['binary.maximum'] = Field(..., description='逐行执行 maximum。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectBinaryMaximumParams = Field(
        default_factory=DirectBinaryMaximumParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_binary_maximum(left, right) {
            /*
            逐元素返回 left 与 right 中较大的值。

            当一侧为标量、另一侧为向量时，标量按元素广播；两个向量输入必须长度一致。

            任一操作数为 NULL 的位置返回 NULL。

            Parameters
            ----------
            left : scalar or vector
                逐元素最大值的第一个候选值。
            right : scalar or vector
                逐元素最大值的第二个候选值。

            Returns
            -------
            result : scalar or vector[NUMBER]
                数值结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：任一侧为 NULL 时结果显式设为 NULL，不像行聚合算符那样跳过缺失值。

            平局与广播：两值相等时返回该值；标量可与向量广播，结果 dtype 使用两侧的公共类型。

            Examples
            --------
            >>> left = 1.0 2.0 4.0
            >>> right = 3.0 2.0 1.0
            >>> direct_binary_maximum(left, right)
            [3, 2, 4]

            二元极值不跳过 NULL：
            >>> isNull(direct_binary_maximum(double([1, NULL]), double([2, 3])))
            [false, true]
            */
            return iif(isNull(left) || isNull(right), NULL, iif(left >= right, left, right))
        }
        """
    )
