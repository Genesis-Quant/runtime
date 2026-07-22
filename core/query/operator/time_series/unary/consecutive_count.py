"""unary.consecutive_count 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import UnaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryConsecutiveCountParams(StrictModel):
    """unary.consecutive_count 不接收参数。"""


class TimeSeriesUnaryConsecutiveCountOperator(TimeSeriesOperator):
    """计算连续 true 数量。"""

    op: Literal['unary.consecutive_count'] = Field(..., description='计算连续 true 数量。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryConsecutiveCountParams = Field(
        default_factory=TimeSeriesUnaryConsecutiveCountParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_consecutive_count(col) {
            /*
            统计当前位置连续为 true 的观测数。

            true 使计数在上一位置基础上加 1，false 或 NULL 将计数重置为 0。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：BOOL NULL 不会新增 true，也不会把已有连续计数清零，而是保持上一计数；false
            才会将计数重置为 0。

            计数语义：true 在上一状态上加 1，结果按观测行计数。若需要 NULL 直接中断连续段，应先把 NULL
            显式转换为 false。

            Examples
            --------
            >>> col = false true true false true true true false
            >>> ts_unary_consecutive_count(col)
            [0, 1, 2, 0, 1, 2, 3, 0]

            NULL 保持已有连续计数：
            >>> ts_unary_consecutive_count(bool([true, NULL, true, true, false]))
            [1, 1, 2, 3, 0]
            */
            return cumPositiveStreak(col)
        }
        """
    )
