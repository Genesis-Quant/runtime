"""unary.mad 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction
from core.query.dolphindb.common import (
    BROADCAST_LIKE,
)

from core.query.operator.base import CrossSectionOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryMadParams(StrictModel):
    """unary.mad 不接收参数。"""


class CrossSectionUnaryMadOperator(CrossSectionOperator):
    """按交易日广播 mad 统计量。"""

    op: Literal['unary.mad'] = Field(..., description='按交易日广播 mad 统计量。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryMadParams = Field(
        default_factory=CrossSectionUnaryMadParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_mad(col) {
            /*
            计算当前截面的中位数绝对离差（MAD）并广播结果。

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
            NULL 处理：截面统计忽略 NULL，并把单个统计量广播到截面全部位置，包括原输入为 NULL
            的位置；没有足够有效样本时广播 NULL。

            输出形状：结果与输入等长，每个位置保存相同统计量。输出为截面中位数绝对偏差的广播向量，而不是逐元素变换。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0
            >>> cs_unary_mad(col)
            [1, 1, 1, 1, 1]

            有效样本足够时，NULL 不阻断截面统计：
            >>> all(!isNull(cs_unary_mad(double([1, NULL, 2, 3, 4, 5]))))
            true
            */
            return broadcast_like(mad(col, true), col)
        }
        """,
        dependencies=(BROADCAST_LIKE,)
    )
