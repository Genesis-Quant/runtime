"""unary.bottom_n 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import CrossSectionOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryBottomNParams(StrictModel):
    """unary.bottom_n 参数。"""

    n: int = Field(..., ge=1, description="需要选择的股票数量。")


class CrossSectionUnaryBottomNOperator(CrossSectionOperator):
    """按交易日执行 bottom_n 选择。"""

    op: Literal['unary.bottom_n'] = Field(..., description='按交易日执行 bottom_n 选择。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryBottomNParams = Field(
        default_factory=CrossSectionUnaryBottomNParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_bottom_n(col, n) {
            /*
            标记当前截面中数值最小的 n 个有效观测。

            选择结果为布尔向量。并列值按原始出现顺序打破平局，使最终入选数量可确定。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。
            n : int
                需要标记的有效观测数量，必须至少为 1。

            Returns
            -------
            result : vector[BOOL]
                与 col 等长的 BOOL 选择标记。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0

            选择 1 个观测：
            >>> cs_unary_bottom_n(col, 1)
            [true, false, false, false, false]

            选择 2 个观测：
            >>> cs_unary_bottom_n(col, 2)
            [true, true, false, false, false]

            选择 3 个观测：
            >>> cs_unary_bottom_n(col, 3)
            [true, true, true, false, false]
            */
            return rank(col, true, , true, `first, false) < int(n)
        }
        """
    )
