"""unary.bars_since 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryBarsSinceParams(StrictModel):
    """unary.bars_since 不接收参数。"""


class TimeSeriesUnaryBarsSinceOperator(TimeSeriesOperator):
    """计算距最近 true 的观测数。"""

    op: Literal['unary.bars_since'] = Field(..., description='计算距最近 true 的观测数。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryBarsSinceParams = Field(
        default_factory=TimeSeriesUnaryBarsSinceParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_bars_since(col) {
            /*
            计算每个位置距最近一次 true 的观测间隔。

            遇到 true 时计数重置为 0，之后每经过一个观测加 1；首次 true 之前没有可用距离，返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的输入向量。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> col = false true true false true true true false
            >>> ts_unary_bars_since(col)
            [NULL, 0, 0, 1, 0, 0, 0, 1]
            */
            n = size(col)
            if (n == 0) return array(INT, 0, 0)
            positions = 0..(n - 1)
            last_position = cummax(iif(nullFill(col, false), positions, int(NULL)))
            return iif(isNull(last_position), int(NULL), positions - last_position)
        }
        """
    )
