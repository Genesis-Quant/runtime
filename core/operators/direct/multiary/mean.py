"""multiary.mean 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import DirectOperator
from core.operators.fields import MultiaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class DirectMultiaryMeanParams(StrictModel):
    """multiary.mean 不接收参数。"""


class DirectMultiaryMeanOperator(DirectOperator):
    """逐行多操作数 mean 归约。"""

    op: Literal['multiary.mean'] = Field(..., description='逐行多操作数 mean 归约。')
    fields: MultiaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: DirectMultiaryMeanParams = Field(
        default_factory=DirectMultiaryMeanParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def direct_multiary_mean(cols) {
            /*
            按位置计算所有非 NULL 操作数的算术平均值。

            计算在每个位置独立进行。数值归约忽略 NULL；某位置没有有效操作数时返回 NULL。

            Parameters
            ----------
            cols : ANY vector
                按位置参与归约的操作数集合；其中的向量长度必须一致。

            Returns
            -------
            result : scalar or vector[NUMBER]
                数值结果；向量输入按元素返回。

            Examples
            --------
            >>> first = 1.0 2.0 3.0
            >>> second = 10.0 20.0 30.0
            >>> cols = array(ANY, 0)
            >>> cols.append!(first)
            >>> cols.append!(second)
            >>> direct_multiary_mean(cols)
            [5.5, 11, 16.5]

            >>> first = 1.0 2.0 3.0
            >>> second = 10.0 20.0 30.0
            >>> first[1] = NULL
            >>> second[2] = NULL
            >>> cols = array(ANY, 0)
            >>> cols.append!(first)
            >>> cols.append!(second)

            NULL 不参与按行归约：
            >>> direct_multiary_mean(cols)
            [5.5, 20, 3]
            */
            return unifiedCall(rowAvg, cols)
        }
        """
    )
