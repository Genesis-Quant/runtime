"""talib.rsi 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibRsiParams(StrictModel):
    """talib.rsi 参数。"""

    time_period: int = Field(..., ge=2, description="技术指标观察周期。")


class TimeSeriesTalibRsiOperator(TimeSeriesOperator):
    """调用 ta::rsi。"""

    op: Literal['talib.rsi'] = Field(..., description='调用 ta::rsi。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibRsiParams = Field(
        default_factory=TimeSeriesTalibRsiParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_rsi(col, time_period) {
            /*
            计算 TA-Lib RSI（相对强弱指标）。

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

            Notes
            -----
            NULL 处理：输入不在算符内填充；TA 函数缺少形成当前指标所需的有效历史时返回 NULL，后续何时恢复由该 ta
            内置函数的窗口状态决定。

            计算定义：根据 Wilder 平滑的平均上涨和平均下跌计算 100 - 100/(1+RS)，结果通常位于 0 到
            100。

            预热与输出：满足指标所需回看周期前返回前置 NULL；周期越长，首个有效结果通常越晚，输出始终与输入序列等长。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1

            time_period=2：
            >>> tail(ts_talib_rsi(close, 2), 3)
            [80.6066, 88.6315, 57.1181]

            time_period=3：
            >>> tail(ts_talib_rsi(close, 3), 3)
            [78.3488, 84.1557, 66.3583]

            time_period=5：
            >>> tail(ts_talib_rsi(close, 5), 3)
            [78.0913, 81.507, 72.1349]
            */
            return ta::rsi(col, int(time_period))
        }
        """
    )
