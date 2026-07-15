"""binary.cross_below 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import BinaryFields
from core.operators.schema import (
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
                左操作数。
            right : vector
                右操作数。

            Returns
            -------
            result : vector[BOOL]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> left = 1.0 2.5 2.0 4.0 3.5 5.0 4.5 6.0
            >>> right = 1.5 2.0 2.5 3.0 4.0 4.5 5.0 5.5
            >>> ts_binary_cross_below(left, right)
            [true, false, true, false, true, false, true, false]
            */
            return (left < right) && (move(left, 1) >= move(right, 1))
        }
        """
    )
