"""unary.expanding_quantile 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction
from core.query.dolphindb.common import (
    MASK_EXPANDING_RESULT,
)

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryExpandingQuantileParams(StrictModel):
    """unary.expanding_quantile 参数。"""

    min_periods: int = Field(default=1, ge=1, description="产生结果所需的最少非空观测数。")
    q: float = Field(..., ge=0, le=1, allow_inf_nan=False, description="目标分位数。")


class TimeSeriesUnaryExpandingQuantileOperator(TimeSeriesOperator):
    """按股票计算扩展分位数。"""

    op: Literal['unary.expanding_quantile'] = Field(..., description='按股票计算扩展分位数。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryExpandingQuantileParams = Field(
        default_factory=TimeSeriesUnaryExpandingQuantileParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_expanding_quantile(col, min_periods, q) {
            /*
            计算从序列起点到当前位置的扩展分位数。

            第 i 个结果使用从序列首个观测到第 i 个观测的全部历史。累计有效观测数小于 min_periods 时返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。
            min_periods : int, default 1
                产生结果所需的累计非 NULL 观测数。未达到该数量的位置返回 NULL。
            q : float
                目标分位数，取值范围为 [0, 1]。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：累计统计忽略 NULL，min_periods 按非 NULL 观测数判断；达到门槛后，当前输入为
            NULL 也可能返回已有历史形成的统计值。

            扩展窗口：q 在每个累计窗口内独立应用，必须位于模型允许的分位数范围。

            Examples
            --------
            >>> col = 1.0 2.0 4.0 3.0 5.0 7.0 6.0 8.0

            min_periods=1：
            >>> ts_unary_expanding_quantile(col, 1, 0.5)
            [1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5]

            min_periods=3：
            >>> ts_unary_expanding_quantile(col, 3, 0.5)
            [NULL, NULL, 2, 2.5, 3, 3.5, 4, 4.5]

            min_periods=5：
            >>> ts_unary_expanding_quantile(col, 5, 0.5)
            [NULL, NULL, NULL, NULL, 3, 3.5, 4, 4.5]
            */
            result = cumpercentile(col, 100 * q)
            return mask_expanding_result(result, col, min_periods)
        }
        """,
        dependencies=(MASK_EXPANDING_RESULT,)
    )
