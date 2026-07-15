"""talib.trange 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import OHLCFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibTrangeParams(StrictModel):
    """talib.trange 不接收参数。"""


class TimeSeriesTalibTrangeOperator(TimeSeriesOperator):
    """调用 ta::trange。"""

    op: Literal['talib.trange'] = Field(..., description='调用 ta::trange。')
    fields: OHLCFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibTrangeParams = Field(
        default_factory=TimeSeriesTalibTrangeParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_trange(high, low, close) {
            /*
            计算 TA-Lib TRANGE（真实波幅）。

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

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> high = close + 0.6
            >>> low = close - 0.5
            >>> tail(ts_talib_trange(high, low, close), 3)
            [1.1, 1.1, 1.1]
            */
            return ta::trange(high, low, close)
        }
        """
    )
