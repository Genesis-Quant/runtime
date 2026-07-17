"""talib.wclPrice 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import OHLCFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibWclPriceParams(StrictModel):
    """talib.wclPrice 不接收参数。"""


class TimeSeriesTalibWclPriceOperator(TimeSeriesOperator):
    """调用 ta::wclPrice。"""

    op: Literal['talib.wclPrice'] = Field(..., description='调用 ta::wclPrice。')
    fields: OHLCFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibWclPriceParams = Field(
        default_factory=TimeSeriesTalibWclPriceParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_wclPrice(high, low, close) {
            /*
            计算 TA-Lib WCLPRICE（加权收盘价）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
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

            Notes
            -----
            NULL 处理：每行所需的任一价格输入为 NULL 时，该行结果为 NULL；函数不前向填充 OHLC 输入。

            计算定义：逐行计算 (high + low + 2*close) / 4，使收盘价权重为其他价格的两倍。

            输出边界：这是逐行价格变换，不需要预热期；结果与输入等长，数值公式由 ta::wclPrice 定义。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> high = close + 0.6
            >>> low = close - 0.5
            >>> tail(ts_talib_wclPrice(high, low, close), 3)
            [12.025, 12.325, 12.125]

            NULL 输入示例：
            >>> high=double([3,NULL]); low=double([1,2]); close=double([2,3])
            >>> ts_talib_wclPrice(high, low, close)
            [2, NULL]
            */
            return ta::wclPrice(high, low, close)
        }
        """
    )
