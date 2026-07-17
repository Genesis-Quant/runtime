"""unary.quantile 算符模型。"""

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


class CrossSectionUnaryQuantileParams(StrictModel):
    """unary.quantile 参数。"""

    q: float = Field(..., ge=0, le=1, allow_inf_nan=False, description="目标分位数。")


class CrossSectionUnaryQuantileOperator(CrossSectionOperator):
    """按交易日广播 quantile 统计量。"""

    op: Literal['unary.quantile'] = Field(..., description='按交易日广播 quantile 统计量。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryQuantileParams = Field(
        default_factory=CrossSectionUnaryQuantileParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_quantile(col, q) {
            /*
            计算当前截面的指定分位数并广播结果。

            统计时忽略 NULL，并把单个截面统计值广播为与 col 等长的向量。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。
            q : float
                目标分位数，取值范围为 [0, 1]。

            Returns
            -------
            result : vector[NUMBER]
                与输入等长的截面数值向量。

            Notes
            -----
            NULL 处理：截面统计忽略 NULL，并把单个统计量广播到截面全部位置，包括原输入为 NULL
            的位置；没有足够有效样本时广播 NULL。

            输出形状：结果与输入等长，每个位置保存相同统计量。q 指定截面分位点；结果是该分位数广播后的向量。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0

            q=0.25：
            >>> cs_unary_quantile(col, 0.25)
            [2, 2, 2, 2, 2]

            q=0.5：
            >>> cs_unary_quantile(col, 0.5)
            [2, 2, 2, 2, 2]

            q=0.75：
            >>> cs_unary_quantile(col, 0.75)
            [4, 4, 4, 4, 4]
            */
            return broadcast_like(quantile(col, q), col)
        }
        """,
        dependencies=(BROADCAST_LIKE,)
    )
