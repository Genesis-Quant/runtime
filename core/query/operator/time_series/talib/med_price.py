"""talib.medPrice 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import HighLowFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibMedPriceParams(StrictModel):
    """talib.medPrice 不接收参数。"""


class TimeSeriesTalibMedPriceOperator(TimeSeriesOperator):
    """计算中间价。"""

    op: Literal['talib.medPrice'] = Field(..., description='计算中间价。')
    fields: HighLowFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibMedPriceParams = Field(
        default_factory=TimeSeriesTalibMedPriceParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_medPrice(high, low) {
            /*
            计算 TA-Lib MEDPRICE（中位价格）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
            high : vector
                最高价向量。
            low : vector
                最低价向量。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：每行所需的任一价格输入为 NULL 时，该行结果为 NULL；函数不前向填充 OHLC 输入。

            计算定义：逐行计算 (high + low) / 2。

            输出边界：这是逐行价格变换，不需要预热期；结果与输入等长，数值公式由 ta::medPrice 定义。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> high = close + 0.6
            >>> low = close - 0.5
            >>> tail(ts_talib_medPrice(high, low), 3)
            [12.05, 12.35, 12.15]

            NULL 输入示例：
            >>> high=double([3,NULL]); low=double([1,2])
            >>> ts_talib_medPrice(high, low)
            [2, NULL]
            */
            return ta::medPrice(high, low)
        }
        """
    )
