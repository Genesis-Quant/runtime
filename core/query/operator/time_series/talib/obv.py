"""talib.obv 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import CloseVolumeFields
from core.query.operator.schema import (
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

            Notes
            -----
            NULL 处理：输入不在算符内填充，而是原样交给 TA 状态函数；缺失行可能保持上一累计状态，而不保证在同位置返回
            NULL。需要完整输入时应通过 on 显式排除不完整行。

            计算定义：价格上涨时累加 volume、下跌时扣减 volume、持平时保持，形成累计能量潮。

            状态边界：这是累计状态指标，不需要固定窗口预热；当前输出可能依赖此前全部观测，因此中间缺失值的影响可能延续到后续位置
            。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> volume = long(1000 1200 900 1300 1400 1100 1500 1600 1250 1700 1800 1550)
            >>> tail(ts_talib_obv(close, volume), 3)
            [6450, 8250, 6700]

            NULL 输入示例：
            >>> close=double([1,NULL,2,3]); volume=long([10,20,30,40])
            >>> ts_talib_obv(close, volume)
            [10, 30, 30, 70]
            */
            return ta::obv(close, volume)
        }
        """
    )
