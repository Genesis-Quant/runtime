"""talib.trix 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibTrixParams(StrictModel):
    """talib.trix 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")


class TimeSeriesTalibTrixOperator(TimeSeriesOperator):
    """调用 ta::trix。"""

    op: Literal['talib.trix'] = Field(..., description='调用 ta::trix。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibTrixParams = Field(
        default_factory=TimeSeriesTalibTrixParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_trix(col, time_period) {
            /*
            计算 TA-Lib TRIX（三重指数平滑变化率）。

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
            >>> tail(ts_talib_trix(close, 2), 3)
            [1.7182, 2.15096, 1.09886]

            time_period=3：
            >>> tail(ts_talib_trix(close, 3), 3)
            [1.78664, 1.94317, 1.56171]

            time_period=5：
            >>> tail(ts_talib_trix(close, 5), 3)
            [NULL, NULL, NULL]
            */
            return ta::trix(col, int(time_period))
        }
        """
    )
