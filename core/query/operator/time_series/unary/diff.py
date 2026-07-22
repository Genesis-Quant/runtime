"""unary.diff 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryDiffParams(StrictModel):
    """unary.diff 参数。"""

    periods: int = Field(default=1, ge=1, description="在 on=true 序列中的位移期数。")


class TimeSeriesUnaryDiffOperator(TimeSeriesOperator):
    """按股票执行 diff。"""

    op: Literal['unary.diff'] = Field(..., description='按股票执行 diff。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryDiffParams = Field(
        default_factory=TimeSeriesUnaryDiffParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_diff(col, periods) {
            /*
            计算当前值与指定期数前观测的差。

            periods 按观测条数而不是自然日计数。没有足够历史观测的位置返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。
            periods : int, default 1
                向后比较或位移的观测期数，必须至少为 1。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：当前值或滞后值为 NULL 时结果为 NULL。本算符不跨越缺失观测寻找更早的有效值。

            位置语义：periods 表示序列中的观测间隔，不表示日历天数；前 periods 个位置通常因缺少滞后值而为
            NULL。

            Examples
            --------
            >>> col = 1.0 2.0 4.0 3.0 5.0 7.0 6.0 8.0

            periods=1：
            >>> ts_unary_diff(col, 1)
            [NULL, 1, 2, -1, 2, 2, -1, 2]

            periods=2：
            >>> ts_unary_diff(col, 2)
            [NULL, NULL, 3, 1, 1, 4, 1, 1]

            periods=3：
            >>> ts_unary_diff(col, 3)
            [NULL, NULL, NULL, 2, 3, 3, 3, 3]
            */
            return deltas(col, int(periods))
        }
        """
    )
