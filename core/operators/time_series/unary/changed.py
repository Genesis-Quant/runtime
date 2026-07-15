"""unary.changed 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryChangedParams(StrictModel):
    """unary.changed 参数。"""

    null_equal: bool = Field(default=False, description="两个连续 NULL 是否视为相等。")


class TimeSeriesUnaryChangedOperator(TimeSeriesOperator):
    """判断是否不同于上一条 on=true 观测。"""

    op: Literal['unary.changed'] = Field(..., description='判断是否不同于上一条 on=true 观测。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryChangedParams = Field(
        default_factory=TimeSeriesUnaryChangedParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_changed(col, null_equal) {
            /*
            标记当前值是否相对上一观测发生变化。

            第一个位置固定为 true。一个值为 NULL、另一个非 NULL 时结果为 true；连续两个 NULL 是否算变化由 null_equal 决定。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。
            null_equal : bool, default false
                true 时两个连续 NULL 不算变化；false 时仍标记为变化。

            Returns
            -------
            result : vector[BOOL]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> col = 1.0 1.0 2.0 3.0 4.0 4.0
            >>> col[3 4] = NULL

            连续 NULL 仍视为变化：
            >>> ts_unary_changed(col, false)
            [true, false, true, true, true, true]

            连续 NULL 视为相等：
            >>> ts_unary_changed(col, true)
            [true, false, true, true, false, true]
            */
            n = size(col)
            result = array(BOOL, n, n, false)
            if (n == 0) return result
            previous = move(col, 1)
            current_null = isNull(col)
            previous_null = isNull(previous)
            both_null = current_null && previous_null
            one_null = xor(current_null, previous_null)
            result = iif(one_null, true, iif(both_null, !null_equal, col != previous))
            result[0] = true
            return result
        }
        """
    )
