"""multiary.and 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import MultiaryFields
from core.query.operator.schema import (
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

            计算在每个位置独立进行，并与依次嵌套 binary.and 的结果一致。

            Parameters
            ----------
            cols : ANY vector
                按位置参与归约的操作数集合；其中的向量长度必须一致。

            Returns
            -------
            result : scalar or vector[BOOL]
                布尔结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：任一操作数为 BOOL NULL 时，该位置结果为 NULL，与 binary.and
            使用相同的 NULL 传播规则。

            逻辑边界：按操作数顺序使用 && 归约。所有输入必须具有 BOOL
            语义并在广播后等长。

            Examples
            --------
            >>> first = true true false false
            >>> second = true false true false
            >>> cols = array(ANY, 0)
            >>> cols.append!(first)
            >>> cols.append!(second)
            >>> direct_multiary_and(cols)
            [true, false, false, false]

            任一条件为 NULL 时传播 NULL：
            >>> a = bool([true, false]); b = take(bool(NULL), 2)
            >>> direct_multiary_and([a, b])
            [NULL, NULL]
            */
            result = cols[0]
            if (size(cols) == 1) return result
            for (index in 1..(size(cols) - 1)) result = result && cols[index]
            return result
        }
        """
    )
