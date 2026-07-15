"""talib.linearreg_intercept 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibLinearregInterceptParams(StrictModel):
    """talib.linearreg_intercept 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")


class TimeSeriesTalibLinearregInterceptOperator(TimeSeriesOperator):
    """调用 ta::linearreg_intercept。"""

    op: Literal['talib.linearreg_intercept'] = Field(..., description='调用 ta::linearreg_intercept。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibLinearregInterceptParams = Field(
        default_factory=TimeSeriesTalibLinearregInterceptParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_linearreg_intercept(col, time_period) {
            /*
            计算 TA-Lib LINEARREG_INTERCEPT（滚动线性回归截距）。

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
            >>> tail(ts_talib_linearreg_intercept(close, 2), 3)
            [11.5, 12, 12.3]

            time_period=3：
            >>> tail(ts_talib_linearreg_intercept(close, 3), 3)
            [11.6667, 11.5333, 12.0833]

            time_period=5：
            >>> tail(ts_talib_linearreg_intercept(close, 5), 3)
            [11.06, 11.4, 11.66]
            */
            return ta::linearreg_intercept(col, int(time_period))
        }
        """
    )
