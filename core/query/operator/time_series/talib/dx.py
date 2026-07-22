"""talib.dx 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import OHLCFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibDxParams(StrictModel):
    """talib.dx 参数。"""

    time_period: int = Field(..., ge=2, description="技术指标观察周期。")


class TimeSeriesTalibDxOperator(TimeSeriesOperator):
    """调用 ta::dx。"""

    op: Literal['talib.dx'] = Field(..., description='调用 ta::dx。')
    fields: OHLCFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibDxParams = Field(
        default_factory=TimeSeriesTalibDxParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_dx(high, low, close, time_period) {
            /*
            计算 TA-Lib DX（趋向指数）。

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

            计算定义：计算 100 * abs(+DI - -DI) / (+DI + -DI)，只刻画方向运动差异的强度。

            预热与输出：满足指标所需回看周期前返回前置 NULL；周期越长，首个有效结果通常越晚，输出始终与输入序列等长。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> high = close + 0.6
            >>> low = close - 0.5

            time_period=2：
            >>> tail(ts_talib_dx(high, low, close, 2), 3)
            [61.1239, 77.2323, 14.1616]

            time_period=3：
            >>> tail(ts_talib_dx(high, low, close, 3), 3)
            [57.3137, 68.9242, 32.8025]

            time_period=5：
            >>> tail(ts_talib_dx(high, low, close, 5), 3)
            [55.5548, 62.9101, 43.1661]
            */
            return ta::dx(high, low, close, int(time_period))
        }
        """
    )
