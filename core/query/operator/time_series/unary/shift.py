"""unary.shift 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryShiftParams(StrictModel):
    """unary.shift 参数。"""

    periods: int = Field(default=1, ge=1, description="在 on=true 序列中的位移期数。")


class TimeSeriesUnaryShiftOperator(TimeSeriesOperator):
    """按股票执行 shift。"""

    op: Literal['unary.shift'] = Field(..., description='按股票执行 shift。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryShiftParams = Field(
        default_factory=TimeSeriesUnaryShiftParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_shift(col, periods) {
            /*
            把序列按指定观测期数位移。

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
            NULL 处理：原序列中的 NULL 随位移移动；移出边界的位置丢弃，移入边界的空位使用 typed NULL。

            位置语义：periods 按观测位置而非自然日移动，不跳过 NULL，也不按日期间隔补齐缺失交易日。

            Examples
            --------
            >>> col = 1.0 2.0 4.0 3.0 5.0 7.0 6.0 8.0

            periods=1：
            >>> ts_unary_shift(col, 1)
            [NULL, 1, 2, 4, 3, 5, 7, 6]

            periods=2：
            >>> ts_unary_shift(col, 2)
            [NULL, NULL, 1, 2, 4, 3, 5, 7]

            periods=3：
            >>> ts_unary_shift(col, 3)
            [NULL, NULL, NULL, 1, 2, 4, 3, 5]
            */
            return move(col, int(periods))
        }
        """
    )
