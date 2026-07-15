"""talib.ad 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import OHLCVFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibAdParams(StrictModel):
    """talib.ad 不接收参数。"""


class TimeSeriesTalibAdOperator(TimeSeriesOperator):
    """计算 Chaikin A/D。"""

    op: Literal['talib.ad'] = Field(..., description='计算 Chaikin A/D。')
    fields: OHLCVFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibAdParams = Field(
        default_factory=TimeSeriesTalibAdParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_ad(high, low, close, volume) {
            /*
            计算 TA-Lib AD（累积/派发线）。

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
            >>> tail(ts_talib_ad(high, low, close, volume), 3)
            [-1177.27, -1340.91, -1481.82]
            */
            return ta::ad(high, low, close, volume)
        }
        """
    )
