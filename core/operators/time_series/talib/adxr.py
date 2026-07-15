"""talib.adxr 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import OHLCFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibAdxrParams(StrictModel):
    """talib.adxr 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")


class TimeSeriesTalibAdxrOperator(TimeSeriesOperator):
    """调用 ta::adxr。"""

    op: Literal['talib.adxr'] = Field(..., description='调用 ta::adxr。')
    fields: OHLCFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibAdxrParams = Field(
        default_factory=TimeSeriesTalibAdxrParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_adxr(high, low, close, time_period) {
            /*
            计算 TA-Lib ADXR（平均趋向指数评级）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
            high : vector
                最高价向量。
            low : vector
                最低价向量。
            close : vector
                收盘价向量。
            time_period : int
                技术指标观察周期，必须为正整数；预热期通常返回 NULL。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> high = close + 0.6
            >>> low = close - 0.5

            time_period=2：
            >>> tail(ts_talib_adxr(high, low, close, 2), 3)
            [43.2511, 56.2146, 50.9558]

            time_period=3：
            >>> tail(ts_talib_adxr(high, low, close, 3), 3)
            [60.4019, 56.2579, 52.5246]

            time_period=5：
            >>> tail(ts_talib_adxr(high, low, close, 5), 3)
            [NULL, NULL, NULL]
            */
            return ta::adxr(high, low, close, int(time_period))
        }
        """
    )
