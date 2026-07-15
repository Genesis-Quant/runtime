"""talib.avgPrice 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import FullOHLCFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibAvgPriceParams(StrictModel):
    """talib.avgPrice 不接收参数。"""


class TimeSeriesTalibAvgPriceOperator(TimeSeriesOperator):
    """调用 ta::avgPrice。"""

    op: Literal['talib.avgPrice'] = Field(..., description='调用 ta::avgPrice。')
    fields: FullOHLCFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibAvgPriceParams = Field(
        default_factory=TimeSeriesTalibAvgPriceParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_avgPrice(open, high, low, close) {
            /*
            计算 TA-Lib AVGPRICE（平均价格）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
            open : vector
                开盘价向量。
            high : vector
                最高价向量。
            low : vector
                最低价向量。
            close : vector
                收盘价向量。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> open = close - 0.1
            >>> high = close + 0.6
            >>> low = close - 0.5
            >>> tail(ts_talib_avgPrice(open, high, low, close), 3)
            [12, 12.3, 12.1]
            */
            return ta::avgPrice(open, high, low, close)
        }
        """
    )
