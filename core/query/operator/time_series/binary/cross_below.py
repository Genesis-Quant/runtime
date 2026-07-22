"""binary.cross_below 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import BinaryFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesBinaryCrossBelowParams(StrictModel):
    """binary.cross_below 不接收参数。"""


class TimeSeriesBinaryCrossBelowOperator(TimeSeriesOperator):
    """按股票判断 cross_below。"""

    op: Literal['binary.cross_below'] = Field(..., description='按股票判断 cross_below。')
    fields: BinaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesBinaryCrossBelowParams = Field(
        default_factory=TimeSeriesBinaryCrossBelowParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'BOOL'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_binary_cross_below(left, right) {
            /*
            标记 left 从不低于 right 变为低于 right 的位置。

            只有发生穿越的当前位置返回 true；首个位置以及未发生穿越的位置返回 false。

            Parameters
            ----------
            left : vector
                需要检测交叉的主序列。
            right : vector
                用于比较的基准或阈值序列。

            Returns
            -------
            result : vector[BOOL]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：当前或前一期任一输入为 NULL 时，交叉条件不成立并返回 false；输出不传播 NULL。

            边界语义：首行没有前一期，因此返回 false。只有从非目标侧跨到目标侧才返回
            true，连续停留在目标侧不会重复触发。

            Examples
            --------
            >>> left = 1.0 2.5 2.0 4.0 3.5 5.0 4.5 6.0
            >>> right = 1.5 2.0 2.5 3.0 4.0 4.5 5.0 5.5
            >>> ts_binary_cross_below(left, right)
            [true, false, true, false, true, false, true, false]

            缺失的当前值或前值不会触发交叉：
            >>> ts_binary_cross_below(double([1, NULL, 3, 5]), double([2, 2, 2, NULL]))
            [false, false, false, false]
            */
            previous_left = move(left, 1)
            previous_right = move(right, 1)
            valid = isValid(left) && isValid(right) && isValid(previous_left) && isValid(previous_right)
            return valid && (left < right) && (previous_left >= previous_right)
        }
        """
    )
