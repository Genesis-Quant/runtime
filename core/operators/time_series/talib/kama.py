"""talib.kama 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibKamaParams(StrictModel):
    """talib.kama 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")


class TimeSeriesTalibKamaOperator(TimeSeriesOperator):
    """调用 ta::kama。"""

    op: Literal['talib.kama'] = Field(..., description='调用 ta::kama。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibKamaParams = Field(
        default_factory=TimeSeriesTalibKamaParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_kama(col, time_period) {
            /*
            计算 TA-Lib KAMA（Kaufman 自适应移动平均）。

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

            计算定义：根据价格变化效率比动态调整平滑系数；趋势稳定时响应更快，噪声较大时更平滑。

            预热与输出：满足指标所需回看周期前返回前置 NULL；周期越长，首个有效结果通常越晚，输出始终与输入序列等长。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1

            time_period=2：
            >>> tail(ts_talib_kama(close, 2), 3)
            [11.3059, 11.7477, 11.7598]

            time_period=3：
            >>> tail(ts_talib_kama(close, 3), 3)
            [11.1127, 11.2485, 11.4029]

            time_period=5：
            >>> tail(ts_talib_kama(close, 5), 3)
            [11.4182, 11.6265, 11.6728]
            */
            return ta::kama(col, int(time_period))
        }
        """
    )
