"""talib.adx 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import OHLCFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibAdxParams(StrictModel):
    """talib.adx 参数。"""

    time_period: int = Field(..., ge=2, description="技术指标观察周期。")


class TimeSeriesTalibAdxOperator(TimeSeriesOperator):
    """调用 ta::adx。"""

    op: Literal['talib.adx'] = Field(..., description='调用 ta::adx。')
    fields: OHLCFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibAdxParams = Field(
        default_factory=TimeSeriesTalibAdxParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_adx(high, low, close, time_period) {
            /*
            计算 TA-Lib ADX（平均趋向指数）。

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

            Notes
            -----
            NULL 处理：输入不在算符内填充；TA 函数缺少形成当前指标所需的有效历史时返回 NULL，后续何时恢复由该 ta
            内置函数的窗口状态决定。

            计算定义：由平滑后的正负方向指标计算趋势强度，通常位于 0 到 100；数值不表示趋势方向。

            预热与输出：满足指标所需回看周期前返回前置 NULL；周期越长，首个有效结果通常越晚，输出始终与输入序列等长。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> high = close + 0.6
            >>> low = close - 0.5

            time_period=2：
            >>> tail(ts_talib_adx(high, low, close, 2), 3)
            [49.2087, 63.2205, 38.691]

            time_period=3：
            >>> tail(ts_talib_adx(high, low, close, 3), 3)
            [54.5529, 59.3433, 50.4964]

            time_period=5：
            >>> tail(ts_talib_adx(high, low, close, 5), 3)
            [53.4264, 55.3231, 52.8917]
            */
            return ta::adx(high, low, close, int(time_period))
        }
        """
    )
