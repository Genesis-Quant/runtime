"""multiary.count 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import MultiaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class DirectMultiaryCountParams(StrictModel):
    """multiary.count 不接收参数。"""


class DirectMultiaryCountOperator(DirectOperator):
    """逐行多操作数 count 归约。"""

    op: Literal['multiary.count'] = Field(..., description='逐行多操作数 count 归约。')
    fields: MultiaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectMultiaryCountParams = Field(
        default_factory=DirectMultiaryCountParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_multiary_count(cols) {
            /*
            按位置统计非 NULL 操作数的数量。

            NULL 不计入数量；每个位置的结果范围为 0 到 size(cols)。

            Parameters
            ----------
            cols : ANY vector
                按位置参与归约的操作数集合；其中的向量长度必须一致。

            Returns
            -------
            result : scalar or vector[NUMBER]
                数值结果；向量输入按元素返回。

            Notes
            -----
            NULL 处理：逐行只统计非 NULL 输入；全部为 NULL 的行返回 0。

            形状与类型：所有向量必须等长，标量由执行层广播后参与计算；输出为整数计数向量。

            Examples
            --------
            >>> first = 1.0 2.0 3.0
            >>> second = 10.0 20.0 30.0
            >>> first[1] = NULL
            >>> second[2] = NULL
            >>> cols = array(ANY, 0)
            >>> cols.append!(first)
            >>> cols.append!(second)
            >>> direct_multiary_count(cols)
            [2, 1, 1]

            只统计非 NULL 输入：
            >>> direct_multiary_count([double([1, NULL, NULL]), double([4, 5, NULL])])
            [2, 1, 0]
            */
            return unifiedCall(rowCount, cols)
        }
        """
    )
