"""multiary.and 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import MultiaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectMultiaryAndParams(StrictModel):
    """multiary.and 不接收参数。"""


class DirectMultiaryAndOperator(DirectOperator):
    """多条件逻辑 and。"""

    op: Literal['multiary.and'] = Field(..., description='多条件逻辑 and。')
    fields: MultiaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectMultiaryAndParams = Field(
        default_factory=DirectMultiaryAndParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_multiary_and(cols) {
            /*
            按位置计算所有布尔操作数的逻辑与。

            计算在每个位置独立进行。数值归约忽略 NULL；某位置没有有效操作数时返回 NULL。

            Parameters
            ----------
            cols : ANY vector
                按位置参与归约的操作数集合；其中的向量长度必须一致。

            Returns
            -------
            result : scalar or vector[BOOL]
                布尔结果；向量输入按元素返回。

            Examples
            --------
            >>> first = true true false false
            >>> second = true false true false
            >>> cols = array(ANY, 0)
            >>> cols.append!(first)
            >>> cols.append!(second)
            >>> direct_multiary_and(cols)
            [true, false, false, false]
            */
            return unifiedCall(rowAnd, cols)
        }
        """
    )
