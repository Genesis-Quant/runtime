"""multiary.min 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import DirectOperator
from core.query.operator.fields import MultiaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class DirectMultiaryMinParams(StrictModel):
    """multiary.min 不接收参数。"""


class DirectMultiaryMinOperator(DirectOperator):
    """逐行多操作数 min 归约。"""

    op: Literal['multiary.min'] = Field(..., description='逐行多操作数 min 归约。')
    fields: MultiaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectMultiaryMinParams = Field(
        default_factory=DirectMultiaryMinParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_multiary_min(cols) {
            /*
            按位置返回所有操作数中的最小值。

            计算在每个位置独立进行。数值归约忽略 NULL；某位置没有有效操作数时返回 NULL。

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
            NULL 处理：逐行数值聚合忽略 NULL，只使用该行的有效输入；整行全部为 NULL 时返回 NULL。

            形状与类型：输入在执行前广播为等长向量，输出每行一个数值。该语义不同于普通二元算术算符的 NULL 传播。

            Examples
            --------
            >>> first = 1.0 2.0 3.0
            >>> second = 10.0 20.0 30.0
            >>> cols = array(ANY, 0)
            >>> cols.append!(first)
            >>> cols.append!(second)
            >>> direct_multiary_min(cols)
            [1, 2, 3]

            >>> first = 1.0 2.0 3.0
            >>> second = 10.0 20.0 30.0
            >>> first[1] = NULL
            >>> second[2] = NULL
            >>> cols = array(ANY, 0)
            >>> cols.append!(first)
            >>> cols.append!(second)

            NULL 不参与按行归约：
            >>> direct_multiary_min(cols)
            [1, 20, 3]
            */
            return unifiedCall(rowMin, cols)
        }
        """
    )
