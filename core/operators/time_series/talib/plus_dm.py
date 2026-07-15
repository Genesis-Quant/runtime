"""talib.plus_dm 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import HighLowFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibPlusDmParams(StrictModel):
    """talib.plus_dm 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")


class TimeSeriesTalibPlusDmOperator(TimeSeriesOperator):
    """调用 ta::plus_dm。"""

    op: Literal['talib.plus_dm'] = Field(..., description='调用 ta::plus_dm。')
    fields: HighLowFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibPlusDmParams = Field(
        default_factory=TimeSeriesTalibPlusDmParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_plus_dm(high, low, time_period) {
            /*
            计算 TA-Lib PLUS_DM（正向运动）。

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

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> high = close + 0.6
            >>> low = close - 0.5

            time_period=2：
            >>> tail(ts_talib_plus_dm(high, low, 2), 3)
            [0.683203, 0.641602, 0.320801]

            time_period=3：
            >>> tail(ts_talib_plus_dm(high, low, 3), 3)
            [0.947371, 0.931581, 0.621054]

            time_period=5：
            >>> tail(ts_talib_plus_dm(high, low, 5), 3)
            [1.47075, 1.4766, 1.18128]
            */
            return ta::plus_dm(high, low, int(time_period))
        }
        """
    )
