"""talib.aroonOsc 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import HighLowFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibAroonOscParams(StrictModel):
    """talib.aroonOsc 参数。"""

    time_period: int = Field(..., ge=2, description="技术指标观察周期。")


class TimeSeriesTalibAroonOscOperator(TimeSeriesOperator):
    """调用 ta::aroonOsc。"""

    op: Literal['talib.aroonOsc'] = Field(..., description='调用 ta::aroonOsc。')
    fields: HighLowFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibAroonOscParams = Field(
        default_factory=TimeSeriesTalibAroonOscParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_aroonOsc(high, low, time_period) {
            /*
            计算 TA-Lib AROONOSC（Aroon 振荡器）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
            high : vector
                最高价向量。
            low : vector
                最低价向量。
            time_period : int
                技术指标观察周期，必须为正整数；预热期通常返回 NULL。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：输入不在算符内填充；TA 函数缺少形成当前指标所需的有效历史时返回 NULL，后续何时恢复由该 ta
            内置函数的窗口状态决定。

            计算定义：返回 Aroon Up 减 Aroon Down，用正负号表达上涨或下跌趋势占优。

            预热与输出：满足指标所需回看周期前返回前置 NULL；周期越长，首个有效结果通常越晚，输出始终与输入序列等长。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> high = close + 0.6
            >>> low = close - 0.5

            time_period=2：
            >>> tail(ts_talib_aroonOsc(high, low, 2), 3)
            [50, 100, 50]

            time_period=3：
            >>> tail(ts_talib_aroonOsc(high, low, 3), 3)
            [100, 66.6667, 66.6667]

            time_period=5：
            >>> tail(ts_talib_aroonOsc(high, low, 5), 3)
            [80, 100, 80]
            */
            result = ta::aroonOsc(high, low, int(time_period))
            valid = isValid(high) && isValid(low)
            first = ifirstNot(iif(valid, 1, int(NULL)))
            if (first < 0) return result
            positions = 0..(size(result) - 1)
            return iif(positions < first + int(time_period), double(NULL), result)
        }
        """
    )
