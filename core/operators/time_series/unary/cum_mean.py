"""unary.cum_mean 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    MASK_EXPANDING_RESULT,
)

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryCumMeanParams(StrictModel):
    """unary.cum_mean 参数。"""

    min_periods: int = Field(default=1, ge=1, description="产生结果所需的最少非空观测数。")


class TimeSeriesUnaryCumMeanOperator(TimeSeriesOperator):
    """按股票执行 cum_mean。"""

    op: Literal['unary.cum_mean'] = Field(..., description='按股票执行 cum_mean。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryCumMeanParams = Field(
        default_factory=TimeSeriesUnaryCumMeanParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_cum_mean(col, min_periods) {
            /*
            计算截至当前位置的累计平均值。

            第 i 个结果使用从序列起点到当前位置的有效观测。累计有效观测数小于 min_periods 时返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。
            min_periods : int, default 1
                产生结果所需的累计非 NULL 观测数。未达到该数量的位置返回 NULL。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> col = 1.0 2.0 4.0 3.0 5.0 7.0 6.0 8.0

            min_periods=1：
            >>> ts_unary_cum_mean(col, 1)
            [1, 1.5, 2.33333, 2.5, 3, 3.66667, 4, 4.5]

            min_periods=3：
            >>> ts_unary_cum_mean(col, 3)
            [NULL, NULL, 2.33333, 2.5, 3, 3.66667, 4, 4.5]
            */
            result = cumavg(col)
            return mask_expanding_result(result, col, min_periods)
        }
        """,
        dependencies=(MASK_EXPANDING_RESULT,)
    )
