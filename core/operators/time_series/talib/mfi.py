"""talib.mfi 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import OHLCVFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibMfiParams(StrictModel):
    """talib.mfi 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")


class TimeSeriesTalibMfiOperator(TimeSeriesOperator):
    """计算资金流量指标。"""

    op: Literal['talib.mfi'] = Field(..., description='计算资金流量指标。')
    fields: OHLCVFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibMfiParams = Field(
        default_factory=TimeSeriesTalibMfiParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_mfi(high, low, close, volume, time_period) {
            /*
            计算 TA-Lib MFI（资金流量指标）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
            high : vector
                最高价向量。
            low : vector
                最低价向量。
            close : vector
                收盘价向量。
            volume : vector
                成交量向量。
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
            >>> volume = long(1000 1200 900 1300 1400 1100 1500 1600 1250 1700 1800 1550)

            time_period=2：
            >>> tail(ts_talib_mfi(high, low, close, volume, 2), 3)
            [58.6599, 100, 54.1375]

            time_period=3：
            >>> tail(ts_talib_mfi(high, low, close, volume, 3), 3)
            [73.2065, 74.7401, 69.4018]

            time_period=5：
            >>> tail(ts_talib_mfi(high, low, close, volume, 5), 3)
            [68.1342, 84.5243, 64.9592]
            */
            return ta::mfi(high, low, close, volume, int(time_period))
        }
        """
    )
