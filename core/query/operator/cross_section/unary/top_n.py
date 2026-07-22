"""unary.top_n 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import CrossSectionOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryTopNParams(StrictModel):
    """unary.top_n 参数。"""

    n: int = Field(..., ge=1, description="需要选择的股票数量。")


class CrossSectionUnaryTopNOperator(CrossSectionOperator):
    """按交易日执行 top_n 选择。"""

    op: Literal['unary.top_n'] = Field(..., description='按交易日执行 top_n 选择。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryTopNParams = Field(
        default_factory=CrossSectionUnaryTopNParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_top_n(col, n) {
            /*
            标记当前截面中数值最大的 n 个有效观测。

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

            Notes
            -----
            NULL 处理：排名只使用非 NULL 观测，原输入为 NULL 的位置明确返回
            false，不会占用顶部或底部的选择名额。全 NULL 截面返回全 false。

            选择边界：按降序选择最多 n 个有效观测；n 超过有效样本数时全体有效值入选。并列值以 first
            规则按原顺序打破。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0

            选择 1 个观测：
            >>> cs_unary_top_n(col, 1)
            [false, false, false, false, true]

            选择 2 个观测：
            >>> cs_unary_top_n(col, 2)
            [false, false, false, true, true]

            选择 3 个观测：
            >>> cs_unary_top_n(col, 3)
            [false, true, false, true, true]
            */
            return !isNull(col) && (rank(col, false, , true, `first, false) < int(n))
        }
        """
    )
