"""nullary.false 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import NullaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class DirectNullaryFalseParams(StrictModel):
    """nullary.false 不接收参数。"""


class DirectNullaryFalseOperator(DirectOperator):
    """广播 false。"""

    op: Literal['nullary.false'] = Field(..., description='广播 false。')
    fields: NullaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectNullaryFalseParams = Field(
        default_factory=DirectNullaryFalseParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_nullary_false() {
            /*
            返回布尔标量 false。

            Parameters
            ----------
            None
                此函数不接收参数。

            Returns
            -------
            result : BOOL
                布尔结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：函数没有输入值，因此不会接收或传播 NULL；每次调用都返回非 NULL 的 BOOL 标量
            false。

            形状与用途：函数本身只返回标量。需要与向量配合时，由调用表达式显式广播，不能把它理解为已经具有输入表行数的布尔列。

            Examples
            --------
            >>> direct_nullary_false()
            false

            广播为三元素掩码：
            >>> take(direct_nullary_false(), 3)
            [false, false, false]
            */
            return false
        }
        """
    )
