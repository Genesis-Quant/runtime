"""talib.var 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibVarParams(StrictModel):
    """talib.var 参数。"""

    time_period: int = Field(..., ge=1, description="技术指标观察周期。")
    nbdev: float = Field(default=1.0, gt=0, allow_inf_nan=False, description="标准差倍数。")


class TimeSeriesTalibVarOperator(TimeSeriesOperator):
    """调用 ta::var。"""

    op: Literal['talib.var'] = Field(..., description='调用 ta::var。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibVarParams = Field(
        default_factory=TimeSeriesTalibVarParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_var(col, time_period, nbdev) {
            /*
            计算 TA-Lib VAR（滚动方差）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的数值序列。
            time_period : int
                技术指标观察周期，必须为正整数；预热期通常返回 NULL。
            nbdev : float, default 1.0
                标准差结果的缩放倍数。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：输入不在算符内填充；TA 函数缺少形成当前指标所需的有效历史时返回 NULL，后续何时恢复由该 ta
            内置函数的窗口状态决定。

            计算定义：计算 time_period 窗口方差，并按 TA-Lib 的 nbdev 参数缩放。

            预热与输出：满足指标所需回看周期前返回前置 NULL；周期越长，首个有效结果通常越晚，输出始终与输入序列等长。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1

            nbdev=0.5：
            >>> tail(ts_talib_var(close, 3, 0.5), 3)
            [0.0422222, 0.108889, 0.0155556]

            nbdev=1.0：
            >>> tail(ts_talib_var(close, 3, 1.0), 3)
            [0.0422222, 0.108889, 0.0155556]

            nbdev=2.0：
            >>> tail(ts_talib_var(close, 3, 2.0), 3)
            [0.0422222, 0.108889, 0.0155556]
            */
            return ta::var(col, int(time_period), nbdev)
        }
        """
    )
