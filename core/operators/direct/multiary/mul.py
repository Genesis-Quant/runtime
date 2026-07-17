"""multiary.mul 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import MultiaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectMultiaryMulParams(StrictModel):
    """multiary.mul 不接收参数。"""


class DirectMultiaryMulOperator(DirectOperator):
    """逐行多操作数 mul 归约。"""

    op: Literal['multiary.mul'] = Field(..., description='逐行多操作数 mul 归约。')
    fields: MultiaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectMultiaryMulParams = Field(
        default_factory=DirectMultiaryMulParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_multiary_mul(cols) {
            /*
            按位置计算所有操作数的乘积。

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
            >>> direct_multiary_mul(cols)
            [10, 40, 90]

            >>> first = 1.0 2.0 3.0
            >>> second = 10.0 20.0 30.0
            >>> first[1] = NULL
            >>> second[2] = NULL
            >>> cols = array(ANY, 0)
            >>> cols.append!(first)
            >>> cols.append!(second)

            NULL 不参与按行归约：
            >>> direct_multiary_mul(cols)
            [10, 20, 3]
            */
            return unifiedCall(rowProd, cols)
        }
        """
    )
