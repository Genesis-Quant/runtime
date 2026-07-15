"""talib.linearreg 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibLinearregParams(StrictModel):
    """talib.linearreg 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")


class TimeSeriesTalibLinearregOperator(TimeSeriesOperator):
    """调用 ta::linearreg。"""

    op: Literal['talib.linearreg'] = Field(..., description='调用 ta::linearreg。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibLinearregParams = Field(
        default_factory=TimeSeriesTalibLinearregParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_linearreg(col, time_period) {
            /*
            计算 TA-Lib LINEARREG（滚动线性回归预测值）。

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
            >>> tail(ts_talib_linearreg(close, 2), 3)
            [12, 12.3, 12.1]

            time_period=3：
            >>> tail(ts_talib_linearreg(close, 3), 3)
            [11.8667, 12.3333, 12.1833]

            time_period=5：
            >>> tail(ts_talib_linearreg(close, 5), 3)
            [11.98, 12.2, 12.22]
            */
            return ta::linearreg(col, int(time_period))
        }
        """
    )
