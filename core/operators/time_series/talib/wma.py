"""talib.wma 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibWmaParams(StrictModel):
    """talib.wma 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")


class TimeSeriesTalibWmaOperator(TimeSeriesOperator):
    """调用 ta::wma。"""

    op: Literal['talib.wma'] = Field(..., description='调用 ta::wma。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibWmaParams = Field(
        default_factory=TimeSeriesTalibWmaParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_wma(col, time_period) {
            /*
            计算 TA-Lib WMA（加权移动平均）。

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
            >>> tail(ts_talib_wma(close, 2), 3)
            [11.8333, 12.2, 12.1667]

            time_period=3：
            >>> tail(ts_talib_wma(close, 3), 3)
            [11.8, 12.0667, 12.15]

            time_period=5：
            >>> tail(ts_talib_wma(close, 5), 3)
            [11.6733, 11.9333, 12.0333]
            */
            return ta::wma(col, int(time_period))
        }
        """
    )
