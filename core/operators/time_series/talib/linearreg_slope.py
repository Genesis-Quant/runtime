"""talib.linearreg_slope 算符模型。"""

from typing import ClassVar, Literal

from pydantic import Field

from core.dolphindb import DolphinDBFunction

from core.operators.base import TimeSeriesOperator
from core.operators.fields import UnaryFields
from core.operators.schema import (
    OutputKind,
    StrictModel,
)


class TimeSeriesTalibLinearregSlopeParams(StrictModel):
    """talib.linearreg_slope 参数。"""

    time_period: int = Field(..., ge=2, description="技术指标观察周期。")


class TimeSeriesTalibLinearregSlopeOperator(TimeSeriesOperator):
    """调用 ta::linearreg_slope。"""

    op: Literal['talib.linearreg_slope'] = Field(..., description='调用 ta::linearreg_slope。')
    fields: UnaryFields = Field(..., description="该算符严格定义的输入字段。")
    params: TimeSeriesTalibLinearregSlopeParams = Field(
        default_factory=TimeSeriesTalibLinearregSlopeParams,
        description="该算符严格定义的参数。",
    )
    output_kind: ClassVar[OutputKind] = 'NUMBER'
    function: ClassVar[DolphinDBFunction] = DolphinDBFunction(
        """
        def ts_talib_linearreg_slope(col, time_period) {
            /*
            计算 TA-Lib LINEARREG_SLOPE（滚动线性回归斜率）。

            该函数直接调用 DolphinDB TA-Lib 实现。所有输入向量必须等长；指标尚未积累足够历史观测的预热位置返回 NULL。

            Parameters
            ----------
            col : vector
                按时间升序排列的数值序列。
            time_period : int
                技术指标观察周期，必须为正整数；预热期通常返回 NULL。

            Returns
            -------
            result : vector[NUMBER]
                与输入序列等长；历史观测不足或计算无定义的位置为 NULL。

            Notes
            -----
            NULL 处理：输入不在算符内填充；TA 函数缺少形成当前指标所需的有效历史时返回 NULL，后续何时恢复由该 ta
            内置函数的窗口状态决定。

            计算定义：返回每个滚动位置序号 OLS 拟合直线的斜率。

            预热与输出：满足指标所需回看周期前返回前置 NULL；周期越长，首个有效结果通常越晚，输出始终与输入序列等长。

            Examples
            --------
            >>> close = 10.0 10.5 10.2 10.8 11.1 10.9 11.4 11.8 11.5 12.0 12.3 12.1

            time_period=2：
            >>> tail(ts_talib_linearreg_slope(close, 2), 3)
            [0.5, 0.3, -0.2]

            time_period=3：
            >>> tail(ts_talib_linearreg_slope(close, 3), 3)
            [0.1, 0.4, 0.05]

            time_period=5：
            >>> tail(ts_talib_linearreg_slope(close, 5), 3)
            [0.23, 0.2, 0.14]
            */
            return ta::linearreg_slope(col, int(time_period))
        }
        """
    )
