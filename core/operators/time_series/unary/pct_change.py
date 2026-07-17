"""unary.pct_change 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction
from core.dolphindb.common import (
    DIVIDE_OR_NULL,
)

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesUnaryPctChangeParams(StrictModel):
    """unary.pct_change 参数。"""

    periods: int = Field(default=1, ge=1, description="在 on=true 序列中的位移期数。")


class TimeSeriesUnaryPctChangeOperator(TimeSeriesOperator):
    """按股票执行 pct_change。"""

    op: Literal['unary.pct_change'] = Field(..., description='按股票执行 pct_change。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesUnaryPctChangeParams = Field(
        default_factory=TimeSeriesUnaryPctChangeParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_unary_pct_change(col, periods) {
            /*
            计算相对指定期数前观测的百分比变化。

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
            NULL 处理：当前值或滞后值为 NULL，以及滞后值为 0 时结果为
            NULL。本算符不跨越缺失观测寻找更早的有效值。

            位置语义：periods 表示序列中的观测间隔，不表示日历天数；前 periods 个位置通常因缺少滞后值而为
            NULL。

            Examples
            --------
            >>> col = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8

            periods=1：
            >>> ts_unary_pct_change(col, 1)
            [NULL, 0.05, -0.0285714, 0.0588235, 0.0277778, -0.018018, 0.0458716, 0.0350877]

            periods=2：
            >>> ts_unary_pct_change(col, 2)
            [NULL, NULL, 0.02, 0.0285714, 0.0882353, 0.00925926, 0.027027, 0.0825688]

            periods=3：
            >>> ts_unary_pct_change(col, 3)
            [NULL, NULL, NULL, 0.08, 0.0571429, 0.0686275, 0.0555556, 0.0630631]
            */
            previous = move(col, int(periods))
            return divide_or_null(col, previous) - 1
        }
        """,
        dependencies=(DIVIDE_OR_NULL,)
    )
