"""talib.ad 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import OHLCVFields
from core.query.operator.schema import (
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

            Notes
            -----
            NULL 处理：输入不在算符内填充，而是原样交给 TA 状态函数；缺失行可能保持上一累计状态，而不保证在同位置返回
            NULL。需要完整输入时应通过 on 显式排除不完整行。

            计算定义：按资金流乘数 ((close-low)-(high-close))/(high-low) 乘
            volume，并对资金流量累计求和。

            状态边界：这是累计状态指标，不需要固定窗口预热；当前输出可能依赖此前全部观测，因此中间缺失值的影响可能延续到后续位置
            。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> high = close + 0.6
            >>> low = close - 0.5
            >>> volume = long(1000 1200 900 1300 1400 1100 1500 1600 1250 1700 1800 1550)
            >>> tail(ts_talib_ad(high, low, close, volume), 3)
            [-1177.27, -1340.91, -1481.82]

            NULL 输入示例：
            >>> high=double([2,3,NULL]); low=double([0,1,1]); close=double([1,2,2]); volume=long([10,20,30])
            >>> ts_talib_ad(high, low, close, volume)
            [0, 0, 0]
            */
            return ta::ad(high, low, close, volume)
        }
        """
    )
