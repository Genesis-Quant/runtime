"""nullary.true 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import NullaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectNullaryTrueParams(StrictModel):
    """nullary.true 不接收参数。"""


class DirectNullaryTrueOperator(DirectOperator):
    """广播 true。"""

    op: Literal['nullary.true'] = Field(..., description='广播 true。')
    fields: NullaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectNullaryTrueParams = Field(
        default_factory=DirectNullaryTrueParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_nullary_true() {
            /*
            返回布尔标量 true。

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
            >>> direct_nullary_true()
            true
            */
            return true
        }
        """
    )
