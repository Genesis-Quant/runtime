"""talib.cci 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import OHLCFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibCciParams(StrictModel):
    """talib.cci 参数。"""

    time_period: int = Field(..., ge=2, description="技术指标观察周期。")


class TimeSeriesTalibCciOperator(TimeSeriesOperator):
    """调用 ta::cci。"""

    op: Literal['talib.cci'] = Field(..., description='调用 ta::cci。')
    fields: OHLCFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibCciParams = Field(
        default_factory=TimeSeriesTalibCciParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_cci(high, low, close, time_period) {
            /*
            计算 TA-Lib CCI（顺势指标）。

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

            计算定义：以典型价格为基础，计算其相对移动均值和平均绝对偏差的标准化距离，常数因子为 0.015。

            预热与输出：满足指标所需回看周期前返回前置 NULL；周期越长，首个有效结果通常越晚，输出始终与输入序列等长。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> high = close + 0.6
            >>> low = close - 0.5

            time_period=2：
            >>> tail(ts_talib_cci(high, low, close, 2), 3)
            [66.6667, 66.6667, -66.6667]

            time_period=3：
            >>> tail(ts_talib_cci(high, low, close, 3), 3)
            [87.5, 84.6154, -20]

            time_period=5：
            >>> tail(ts_talib_cci(high, low, close, 5), 3)
            [105.263, 119.048, 45.977]
            */
            return ta::cci(high, low, close, int(time_period))
        }
        """
    )
