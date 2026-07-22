"""talib.ultOsc 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.query.dolphindb import DolphinDBFunction

from core.query.operator.base import TimeSeriesOperator
from core.query.operator.fields import OHLCFields
from core.query.operator.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibUltOscParams(StrictModel):
    """talib.ultOsc 参数。"""

    period1: int = Field(default=7, ge=1, description="短周期。")
    period2: int = Field(default=14, ge=2, description="中周期。")
    period3: int = Field(default=28, ge=3, description="长周期。")

    @model_validator(mode="after")
    def validate_periods(self) -> "TimeSeriesTalibUltOscParams":
        """要求三个周期严格递增。"""
        if not self.period1 < self.period2 < self.period3:
            raise ValueError("params.period1/period2/period3 必须严格递增")
        return self


class TimeSeriesTalibUltOscOperator(TimeSeriesOperator):
    """计算终极振荡指标。"""

    op: Literal['talib.ultOsc'] = Field(..., description='计算终极振荡指标。')
    fields: OHLCFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibUltOscParams = Field(
        default_factory=TimeSeriesTalibUltOscParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_ultOsc(high, low, close, period1, period2, period3) {
            /*
            计算 TA-Lib ULTOSC（终极振荡器）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
            high : vector
                最高价向量。
            low : vector
                最低价向量。
            close : vector
                收盘价向量。
            period1 : int, default 7
                终极振荡器的短周期；必须满足 period1 < period2 < period3。
            period2 : int, default 14
                终极振荡器的中周期；必须满足 period1 < period2 < period3。
            period3 : int, default 28
                终极振荡器的长周期；必须满足 period1 < period2 < period3。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：输入不在算符内填充；TA 函数缺少形成当前指标所需的有效历史时返回 NULL，后续何时恢复由该 ta
            内置函数的窗口状态决定。

            计算定义：分别在 period1/period2/period3 上累计买压与真实波幅，再按 4:2:1
            加权并缩放到 0 到 100。

            预热与输出：满足指标所需回看周期前返回前置 NULL；周期越长，首个有效结果通常越晚，输出始终与输入序列等长。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1
            >>> high = close + 0.6
            >>> low = close - 0.5

            周期组合 2/3/5：
            >>> tail(ts_talib_ultOsc(high, low, close, 2, 3, 5), 3)
            [45.4545, 45.4545, 45.4545]

            周期组合 3/5/7：
            >>> tail(ts_talib_ultOsc(high, low, close, 3, 5, 7), 3)
            [45.5544, 45.4545, 45.4545]

            周期组合 4/6/8：
            >>> tail(ts_talib_ultOsc(high, low, close, 4, 6, 8), 3)
            [45.5421, 45.5421, 45.4545]
            */
            return ta::ultOsc(high, low, close, int(period1), int(period2), int(period3))
        }
        """
    )
