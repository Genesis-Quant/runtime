"""talib.macd 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibMacdParams(StrictModel):
    """talib.macd 参数。"""

    fast_period: int = Field(default=12, ge=1, description="快线周期。")
    slow_period: int = Field(default=26, ge=2, description="慢线周期。")
    signal_period: int = Field(default=9, ge=1, description="信号线周期。")
    output: Literal["macd", "signal", "hist"] = Field(default="macd", description="需要返回的单个输出。")

    @model_validator(mode="after")
    def validate_periods(self) -> "TimeSeriesTalibMacdParams":
        """要求快线周期小于慢线周期。"""
        if self.fast_period >= self.slow_period:
            raise ValueError("params.fast_period 必须小于 params.slow_period")
        return self


class TimeSeriesTalibMacdOperator(TimeSeriesOperator):
    """计算 MACD 并选择单个输出。"""

    op: Literal['talib.macd'] = Field(..., description='计算 MACD 并选择单个输出。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibMacdParams = Field(
        default_factory=TimeSeriesTalibMacdParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_macd(col, fast_period, slow_period, signal_period, output) {
            /*
            计算 TA-Lib MACD（移动平均收敛散度）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            底层指标产生多个向量，output 只选择其中一个返回。

            Parameters
            ----------
            col : vector
                按时间升序排列的数值序列。
            fast_period : int, default 12
                快线周期，必须小于 slow_period。
            slow_period : int, default 26
                慢线周期，必须大于 fast_period。
            signal_period : int, default 9
                MACD 信号线的指数移动平均周期。
            output : {"macd", "signal", "hist"}, default "macd"
                每次调用只返回一个输出向量：
                * "macd"：快线减慢线。
                * "signal"：MACD 的信号移动平均。
                * "hist"：MACD 减信号线。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1

            返回 output="macd"：
            >>> tail(ts_talib_macd(close, 2, 4, 2, "macd"), 3)
            [0.207153, 0.245444, 0.134317]

            返回 output="signal"：
            >>> tail(ts_talib_macd(close, 2, 4, 2, "signal"), 3)
            [0.197262, 0.229383, 0.166006]

            返回 output="hist"：
            >>> tail(ts_talib_macd(close, 2, 4, 2, "hist"), 3)
            [0.00989077, 0.0160607, -0.0316887]

            使用 3/6/2 周期返回 MACD：
            >>> tail(ts_talib_macd(close, 3, 6, 2, "macd"), 3)
            [0.308273, 0.338945, 0.258621]

            使用 3/6/3 周期返回信号线：
            >>> tail(ts_talib_macd(close, 3, 6, 3, "signal"), 3)
            [0.314383, 0.326664, 0.292643]
            */
            values = ta::macd(col, int(fast_period), int(slow_period), int(signal_period))
            if (output == "macd") return values[0]
            if (output == "signal") return values[1]
            return values[2]
        }
        """
    )
