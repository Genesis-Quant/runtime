"""talib.obv 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import CloseVolumeFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibObvParams(StrictModel):
    """talib.obv 不接收参数。"""


class TimeSeriesTalibObvOperator(TimeSeriesOperator):
    """计算 OBV。"""

    op: Literal['talib.obv'] = Field(..., description='计算 OBV。')
    fields: CloseVolumeFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibObvParams = Field(
        default_factory=TimeSeriesTalibObvParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_obv(close, volume) {
            /*
            计算 TA-Lib OBV（能量潮）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
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
            >>> volume = long(1000 1200 900 1300 1400 1100 1500 1600 1250 1700 1800 1550)
            >>> tail(ts_talib_obv(close, volume), 3)
            [6450, 8250, 6700]
            */
            return ta::obv(close, volume)
        }
        """
    )
