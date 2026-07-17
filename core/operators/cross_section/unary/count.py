"""unary.count 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    BROADCAST_LIKE,
)

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryCountParams(StrictModel):
    """unary.count 不接收参数。"""


class CrossSectionUnaryCountOperator(CrossSectionOperator):
    """按交易日广播 count 统计量。"""

    op: Literal['unary.count'] = Field(..., description='按交易日广播 count 统计量。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryCountParams = Field(
        default_factory=CrossSectionUnaryCountParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_count(col) {
            /*
            统计当前截面的非 NULL 观测数并广播结果。

            统计时忽略 NULL，并把单个截面统计值广播为与 col 等长的向量。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Notes
            -----
            NULL 处理：只统计非 NULL 值，并把计数广播到截面全部位置；全 NULL 截面返回 0。

            输出形状：结果与输入等长，每个位置保存相同统计量。输出为有效观测数量的整数广播向量，而不是逐元素有效性标记。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0
            >>> cs_unary_count(col)
            [5, 5, 5, 5, 5]

            只统计有效观测并广播：
            >>> cs_unary_count(double([1, NULL, 3]))
            [2, 2, 2]
            */
            return broadcast_like(count(col), col)
        }
        """,
        dependencies=(BROADCAST_LIKE,)
    )
