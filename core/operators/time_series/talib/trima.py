"""talib.trima 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibTrimaParams(StrictModel):
    """talib.trima 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")


class TimeSeriesTalibTrimaOperator(TimeSeriesOperator):
    """调用 ta::trima。"""

    op: Literal['talib.trima'] = Field(..., description='调用 ta::trima。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibTrimaParams = Field(
        default_factory=TimeSeriesTalibTrimaParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_trima(col, time_period) {
            /*
            计算 TA-Lib TRIMA（三角移动平均）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的数值序列。
            time_period : int
                技术指标观察周期，必须为正整数；预热期通常返回 NULL。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1

            time_period=2：
            >>> tail(ts_talib_trima(close, 2), 3)
            [11.75, 12.15, 12.2]

            time_period=3：
            >>> tail(ts_talib_trima(close, 3), 3)
            [11.7, 11.95, 12.175]

            time_period=5：
            >>> tail(ts_talib_trima(close, 5), 3)
            [11.5667, 11.7556, 11.9444]
            */
            return ta::trima(col, int(time_period))
        }
        """
    )
