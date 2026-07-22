"""unary.bottom_pct 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import CrossSectionOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class CrossSectionUnaryBottomPctParams(StrictModel):
    """unary.bottom_pct 参数。"""

    pct: float = Field(..., gt=0, le=1, allow_inf_nan=False, description="需要选择的截面比例。")


class CrossSectionUnaryBottomPctOperator(CrossSectionOperator):
    """按交易日执行 bottom_pct 选择。"""

    op: Literal['unary.bottom_pct'] = Field(..., description='按交易日执行 bottom_pct 选择。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: CrossSectionUnaryBottomPctParams = Field(
        default_factory=CrossSectionUnaryBottomPctParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def cs_unary_bottom_pct(col, pct) {
            /*
            标记当前截面中位于底部指定比例的有效观测。

            选择结果为布尔向量。并列值按原始出现顺序打破平局，使最终入选数量可确定。

            Parameters
            ----------
            col : vector
                当前截面的数值向量；NULL 不作为有效观测参加统计。
            pct : float
                需要标记的有效观测比例，取值范围为 (0, 1]；数量向上取整。

            Returns
            -------
            result : vector[BOOL]
                与 col 等长的 BOOL 选择标记。

            Notes
            -----
            NULL 处理：排名只使用非 NULL 观测，原输入为 NULL 的位置明确返回
            false，不会占用顶部或底部的选择名额。全 NULL 截面返回全 false。

            选择边界：按升序选择 ceil(有效样本数 * pct) 个观测。并列值以 first 规则按原顺序打破。

            Examples
            --------
            >>> col = 1.0 2.0 2.0 4.0 8.0

            选择 20%：
            >>> cs_unary_bottom_pct(col, 0.2)
            [true, false, false, false, false]

            选择 40%：
            >>> cs_unary_bottom_pct(col, 0.4)
            [true, true, false, false, false]

            选择 60%：
            >>> cs_unary_bottom_pct(col, 0.6)
            [true, true, true, false, false]
            */
            return !isNull(col) && (rank(col, true, , true, `first, false) < ceil(count(col) * pct))
        }
        """
    )
