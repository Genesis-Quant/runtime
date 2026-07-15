"""nullary.false 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import NullaryFields
from core.operators.schema import (
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

            Examples
            --------
            >>> direct_nullary_false()
            false
            */
            return false
        }
        """
    )
