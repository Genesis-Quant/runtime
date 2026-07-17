"""talib.ema 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibEmaParams(StrictModel):
    """talib.ema 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")


class TimeSeriesTalibEmaOperator(TimeSeriesOperator):
    """调用 ta::ema。"""

    op: Literal['talib.ema'] = Field(..., description='调用 ta::ema。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibEmaParams = Field(
        default_factory=TimeSeriesTalibEmaParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_ema(col, time_period) {
            /*
            计算 TA-Lib EMA（指数移动平均）。

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

            计算定义：使用 alpha = 2/(time_period+1) 递推平滑历史值，近期观测权重更高。

            预热与输出：满足指标所需回看周期前返回前置 NULL；周期越长，首个有效结果通常越晚，输出始终与输入序列等长。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1

            time_period=2：
            >>> tail(ts_talib_ema(close, 2), 3)
            [11.8458, 12.1486, 12.1162]

            time_period=3：
            >>> tail(ts_talib_ema(close, 3), 3)
            [11.7409, 12.0204, 12.0602]

            time_period=5：
            >>> tail(ts_talib_ema(close, 5), 3)
            [11.5327, 11.7884, 11.8923]
            */
            return ta::ema(col, int(time_period))
        }
        """
    )
