"""multiary.coalesce 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import MultiaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectMultiaryCoalesceParams(StrictModel):
    """multiary.coalesce 不接收参数。"""


class DirectMultiaryCoalesceOperator(DirectOperator):
    """逐行取第一个非空值。"""

    op: Literal['multiary.coalesce'] = Field(..., description='逐行取第一个非空值。')
    fields: MultiaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectMultiaryCoalesceParams = Field(
        default_factory=DirectMultiaryCoalesceParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'ANY'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_multiary_coalesce(cols) {
            /*
            按位置返回第一个非 NULL 的操作数。

            cols 按给定顺序检查；一旦找到非 NULL 值便停止使用后续操作数。所有操作数均为 NULL 时返回 NULL。

            Parameters
            ----------
            cols : ANY vector
                按位置参与归约的操作数集合；其中的向量长度必须一致。

            Returns
            -------
            result : scalar or vector
                按优先级得到的公共类型结果；向量输入返回广播后的等长向量。

            Notes
            -----
            NULL 处理：按 cols 顺序返回每一行第一个非 NULL 值；该行所有输入均为 NULL 时结果为 NULL。

            顺序与类型：列顺序决定优先级，后续列只填补前面仍为空的位置；结果 dtype 由所有候选输入的公共类型决定。

            Examples
            --------
            >>> first = 1.0 2.0 3.0
            >>> second = 10.0 20.0 30.0
            >>> first[1] = NULL
            >>> second[2] = NULL
            >>> cols = array(ANY, 0)
            >>> cols.append!(first)
            >>> cols.append!(second)
            >>> direct_multiary_coalesce(cols)
            [1, 20, 3]

            整行都缺失时保留 NULL：
            >>> direct_multiary_coalesce([double([1, NULL, NULL]), double([4, 5, NULL])])
            [1, 5, NULL]
            */
            result = cols[size(cols) - 1]
            if (size(cols) > 1) {
                for (index in (size(cols) - 2)..0) result = nullFill(cols[index], result)
            }
            return result
        }
        """
    )
