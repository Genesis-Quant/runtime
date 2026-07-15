"""talib.aroon 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import HighLowFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibAroonParams(StrictModel):
    """talib.aroon 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")
    output: Literal["down", "up"] = Field(default="up", description="需要返回的单个输出。")


class TimeSeriesTalibAroonOperator(TimeSeriesOperator):
    """计算 Aroon 并选择单个输出。"""

    op: Literal['talib.aroon'] = Field(..., description='计算 Aroon 并选择单个输出。')
    fields: HighLowFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibAroonParams = Field(
        default_factory=TimeSeriesTalibAroonParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_aroon(high, low, time_period, output) {
            /*
            计算 TA-Lib AROON（Aroon 上升线或下降线）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            底层指标产生多个向量，output 只选择其中一个返回。

            Parameters
            ----------
            high : vector
                最高价向量。
            low : vector
                最低价向量。
            time_period : int
                技术指标观察周期，必须为正整数；预热期通常返回 NULL。
            output : {"down", "up"}, default "up"
                每次调用只返回一个输出向量：
                * "down"：Aroon 下降线。
                * "up"：Aroon 上升线。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> high = close + 0.6
            >>> low = close - 0.5

            返回 output="down"：
            >>> tail(ts_talib_aroon(high, low, 3, "down"), 3)
            [0, 33.3333, 0]

            返回 output="up"：
            >>> tail(ts_talib_aroon(high, low, 3, "up"), 3)
            [100, 100, 66.6667]

            两期下降线：
            >>> tail(ts_talib_aroon(high, low, 2, "down"), 3)
            [50, 0, 0]

            两期上升线：
            >>> tail(ts_talib_aroon(high, low, 2, "up"), 3)
            [100, 100, 50]

            五期下降线：
            >>> tail(ts_talib_aroon(high, low, 5, "down"), 3)
            [20, 0, 0]

            五期上升线：
            >>> tail(ts_talib_aroon(high, low, 5, "up"), 3)
            [100, 100, 80]
            */
            values = ta::aroon(high, low, int(time_period))
            if (output == "down") return values[0]
            return values[1]
        }
        """
    )
